"""使用 Kafka 手动提交 offset 实现至少一次任务消费。"""

import asyncio
import ssl
from collections.abc import Iterable
from functools import partial

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, ConsumerRebalanceListener, TopicPartition

from app.config.queue import KafkaQueueSettings
from app.infrastructure.queue.errors import DeliveryLostError, QueueError
from app.infrastructure.resources.lazy import AsyncLazy


def client_options(settings: KafkaQueueSettings) -> dict[str, object]:
    """把统一配置转换成生产者和消费者共享的客户端参数。"""

    return {
        "bootstrap_servers": settings.bootstrap_servers,
        "security_protocol": settings.security_protocol,
        "ssl_context": ssl.create_default_context() if "SSL" in settings.security_protocol else None,
        "sasl_mechanism": settings.sasl_mechanism,
        "sasl_plain_username": settings.username,
        "sasl_plain_password": settings.password.get_secret_value() if settings.password else None,
    }


class KafkaDelivery:
    """绑定一条 Kafka 记录及其所属的消费组 generation。"""

    def __init__(
        self,
        source: KafkaConsumer,
        partition: TopicPartition,
        offset: int,
        payload: bytes,
        generation: int,
        *,
        possibly_redelivered: bool,
    ) -> None:
        """绑定消息位置、消费代次和负责执行该消息的任务。"""

        self.source = source
        self.partition = partition
        self.offset = offset
        self.payload = payload
        self.identity = f"{partition.topic}:{partition.partition}:{offset}"
        self.generation = generation
        self.possibly_redelivered = possibly_redelivered
        self.owner = asyncio.current_task()
        self.settled = False

    async def acknowledge(self) -> None:
        """提交下一 offset；再均衡后的旧 delivery 禁止继续确认。"""

        if self.settled or self.source.closed or self.generation != self.source.generation:
            raise DeliveryLostError("Kafka delivery 已失效")
        # Kafka 提交值表示下一条要读取的记录，因此确认 offset N 时提交 N + 1。
        await self.source.client.commit({self.partition: self.offset + 1})
        if self.generation != self.source.generation:
            raise DeliveryLostError("Kafka 确认期间发生再均衡")
        self.settled = True
        self.source.pending.pop(self.partition, None)
        # 同一 generation 内成功提交后，后续 offset 可视为本消费者首次投递。
        self.source.trusted_partitions.add(self.partition)
        self.source.client.resume(self.partition)


class RebalanceListener(ConsumerRebalanceListener):
    """在分区所有权变化时让旧的在途执行失效。"""

    def __init__(self, source: KafkaConsumer) -> None:
        """保存需要响应分区所有权变化的消费者。"""

        self.source = source

    async def on_partitions_revoked(self, revoked: Iterable[TopicPartition]) -> None:
        """在分区撤销时取消全部旧 generation 的在途执行。"""

        revoked_partitions = tuple(revoked)
        # 取消旧 generation 的 handler，避免其完成后提交已经转移的分区。
        self.source.generation += 1
        self.source.trusted_partitions.difference_update(revoked_partitions)
        for delivery in tuple(self.source.pending.values()):
            if delivery.owner is not None:
                delivery.owner.cancel()
        self.source.pending.clear()

    async def on_partitions_assigned(self, assigned: Iterable[TopicPartition]) -> None:
        """恢复新分配分区的消息拉取。"""

        assigned_partitions = tuple(assigned)
        # 新 assignment 的首条消息可能来自前一消费者未提交的执行。
        self.source.trusted_partitions.difference_update(assigned_partitions)
        self.source.client.resume(*assigned_partitions)


class KafkaConsumer:
    """保证同一分区只有一条未确认任务，同时允许跨分区并发。"""

    def __init__(self, settings: KafkaQueueSettings, queue: str) -> None:
        """创建尚未启动的客户端，并订阅指定逻辑队列。"""

        self.client = AIOKafkaConsumer(
            **client_options(settings),
            group_id=settings.group,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            max_poll_interval_ms=settings.max_poll_interval_ms,
        )
        self.pending: dict[TopicPartition, KafkaDelivery] = {}
        self.trusted_partitions: set[TopicPartition] = set()
        self.generation = 0
        self.closed = False
        self._lock = asyncio.Lock()
        self.client.subscribe(topics=(queue,), listener=RebalanceListener(self))

    async def receive(self) -> KafkaDelivery:
        """读取并暂停消息所属分区，直到 delivery 被确认。"""

        async with self._lock:
            if self.closed:
                raise QueueError("Kafka 消费者已关闭")
            record = await self.client.getone()
            partition = TopicPartition(record.topic, record.partition)
            if partition in self.pending:
                raise DeliveryLostError("Kafka 分区已有未确认任务")
            # 暂停当前分区可防止多个执行槽并行处理同一分区的后续消息。
            self.client.pause(partition)
            delivery = KafkaDelivery(
                self,
                partition,
                record.offset,
                record.value or b"",
                self.generation,
                possibly_redelivered=partition not in self.trusted_partitions,
            )
            self.pending[partition] = delivery
            return delivery

    async def aclose(self) -> None:
        """标记消费者关闭，并停止客户端的消费组会话。"""

        self.closed = True
        await self.client.stop()


class KafkaBackend:
    """共享一个延迟创建的 Producer，并为每个 Worker 创建 Consumer。"""

    def __init__(self, settings: KafkaQueueSettings) -> None:
        """保存连接配置，并建立延迟 Producer 资源。"""

        self._settings = settings
        self._producer = AsyncLazy(partial(_create_producer, settings), _close_producer)

    @classmethod
    async def create(cls, settings: KafkaQueueSettings) -> KafkaBackend:
        """构建后端但不提前连接 Producer。"""

        return cls(settings)

    async def publish(self, queue: str, payload: bytes) -> None:
        """延迟启动 Producer，并等待 Broker 确认消息发送。"""

        await (await self._producer.get()).send_and_wait(queue, payload)

    async def consumer(self, queue: str, concurrency: int) -> KafkaConsumer:
        """创建并启动订阅单个逻辑队列的消费组成员。"""

        consumer = KafkaConsumer(self._settings, queue)
        try:
            await consumer.client.start()
        except BaseException:
            await consumer.aclose()
            raise
        return consumer

    async def aclose(self) -> None:
        """关闭已经创建的共享 Producer；未使用时不建立连接。"""

        await self._producer.aclose()


async def _create_producer(settings: KafkaQueueSettings) -> AIOKafkaProducer:
    """创建启用幂等和全部副本确认的 Kafka Producer。"""

    producer = AIOKafkaProducer(**client_options(settings), enable_idempotence=True, acks="all")
    try:
        await producer.start()
    except BaseException:
        await producer.stop()
        raise
    return producer


async def _close_producer(producer: AIOKafkaProducer) -> None:
    """停止 Kafka Producer 并释放网络资源。"""

    await producer.stop()
