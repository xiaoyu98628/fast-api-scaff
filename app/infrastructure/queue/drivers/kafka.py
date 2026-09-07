import asyncio
import ssl
from collections.abc import Iterable
from functools import partial

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, ConsumerRebalanceListener, TopicPartition

from app.config.queue import KafkaQueueSettings
from app.infrastructure.queue.errors import DeliveryLostError, QueueError
from app.infrastructure.resources.lazy import AsyncLazy


def client_options(settings: KafkaQueueSettings) -> dict[str, object]:
    return {
        "bootstrap_servers": settings.bootstrap_servers,
        "security_protocol": settings.security_protocol,
        "ssl_context": ssl.create_default_context() if "SSL" in settings.security_protocol else None,
        "sasl_mechanism": settings.sasl_mechanism,
        "sasl_plain_username": settings.username,
        "sasl_plain_password": settings.password.get_secret_value() if settings.password else None,
    }


class KafkaDelivery:
    def __init__(self, source: KafkaConsumer, partition: TopicPartition, offset: int, payload: bytes, generation: int) -> None:
        self.source = source
        self.partition = partition
        self.offset = offset
        self.payload = payload
        self.identity = f"{partition.topic}:{partition.partition}:{offset}"
        self.generation = generation
        self.owner = asyncio.current_task()
        self.settled = False

    async def acknowledge(self) -> None:
        if self.settled or self.source.closed or self.generation != self.source.generation:
            raise DeliveryLostError("Kafka delivery 已失效")
        await self.source.client.commit({self.partition: self.offset + 1})
        if self.generation != self.source.generation:
            raise DeliveryLostError("Kafka 确认期间发生再均衡")
        self.settled = True
        self.source.pending.pop(self.partition, None)
        self.source.client.resume(self.partition)


class RebalanceListener(ConsumerRebalanceListener):
    def __init__(self, source: KafkaConsumer) -> None:
        self.source = source

    async def on_partitions_revoked(self, revoked: Iterable[TopicPartition]) -> None:
        self.source.generation += 1
        for delivery in tuple(self.source.pending.values()):
            if delivery.owner is not None:
                delivery.owner.cancel()
        self.source.pending.clear()

    async def on_partitions_assigned(self, assigned: Iterable[TopicPartition]) -> None:
        self.source.client.resume(*assigned)


class KafkaConsumer:
    def __init__(self, settings: KafkaQueueSettings, queue: str) -> None:
        self.client = AIOKafkaConsumer(
            **client_options(settings),
            group_id=settings.group,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            max_poll_interval_ms=settings.max_poll_interval_ms,
        )
        self.pending: dict[TopicPartition, KafkaDelivery] = {}
        self.generation = 0
        self.closed = False
        self._lock = asyncio.Lock()
        self.client.subscribe(topics=(queue,), listener=RebalanceListener(self))

    async def receive(self) -> KafkaDelivery:
        async with self._lock:
            if self.closed:
                raise QueueError("Kafka 消费者已关闭")
            record = await self.client.getone()
            partition = TopicPartition(record.topic, record.partition)
            if partition in self.pending:
                raise DeliveryLostError("Kafka 分区已有未确认任务")
            self.client.pause(partition)
            delivery = KafkaDelivery(self, partition, record.offset, record.value or b"", self.generation)
            self.pending[partition] = delivery
            return delivery

    async def aclose(self) -> None:
        self.closed = True
        await self.client.stop()


class KafkaBackend:
    def __init__(self, settings: KafkaQueueSettings) -> None:
        self._settings = settings
        self._producer = AsyncLazy(partial(_create_producer, settings), _close_producer)

    @classmethod
    async def create(cls, settings: KafkaQueueSettings) -> KafkaBackend:
        return cls(settings)

    async def publish(self, queue: str, payload: bytes) -> None:
        await (await self._producer.get()).send_and_wait(queue, payload)

    async def consumer(self, queue: str, concurrency: int) -> KafkaConsumer:
        consumer = KafkaConsumer(self._settings, queue)
        try:
            await consumer.client.start()
        except BaseException:
            await consumer.aclose()
            raise
        return consumer

    async def aclose(self) -> None:
        await self._producer.aclose()


async def _create_producer(settings: KafkaQueueSettings) -> AIOKafkaProducer:
    producer = AIOKafkaProducer(**client_options(settings), enable_idempotence=True, acks="all")
    try:
        await producer.start()
    except BaseException:
        await producer.stop()
        raise
    return producer


async def _close_producer(producer: AIOKafkaProducer) -> None:
    await producer.stop()
