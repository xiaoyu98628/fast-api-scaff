"""使用 RabbitMQ 持久队列和手动 ACK 实现任务消费。"""

import asyncio

import aio_pika
from aio_pika.abc import AbstractChannel, AbstractConnection, AbstractIncomingMessage, AbstractQueueIterator

from app.config.queue import RabbitMQQueueSettings
from app.infrastructure.queue.errors import QueueError


class RabbitDelivery:
    """适配一条尚未确认的 RabbitMQ 消息。"""

    def __init__(self, message: AbstractIncomingMessage) -> None:
        """包装一条未确认消息，并生成稳定的消费身份。"""

        self._message = message
        self.payload = message.body
        self.identity = message.message_id or f"delivery:{message.delivery_tag}"
        self.possibly_redelivered = bool(message.redelivered)

    async def acknowledge(self) -> None:
        """向 RabbitMQ 确认当前消息已经处理完毕。"""

        await self._message.ack()


class RabbitConsumer:
    """串行读取一个队列迭代器，并拥有独立消费 Channel。"""

    def __init__(self, channel: AbstractChannel, iterator: AbstractQueueIterator) -> None:
        """接管专用消费 Channel 及其队列迭代器。"""

        self._channel = channel
        self._iterator = iterator
        self._receive_lock = asyncio.Lock()
        self._closed = False

    async def receive(self) -> RabbitDelivery:
        """读取下一条消息；迭代器结束视为消费者故障。"""

        async with self._receive_lock:
            if self._closed:
                raise QueueError("RabbitMQ 消费者已关闭")
            try:
                message = await self._iterator.__anext__()
            except StopAsyncIteration:
                raise QueueError("RabbitMQ 消费流已结束") from None
            return RabbitDelivery(message)

    async def aclose(self) -> None:
        """先停止迭代，再关闭 Channel 以恢复未确认消息。"""

        self._closed = True
        try:
            await self._iterator.close()
        finally:
            await self._channel.close()


class RabbitBackend:
    """复用发布 Channel，并为每个消费者分配独立 Channel。"""

    def __init__(self, connection: AbstractConnection, channel: AbstractChannel) -> None:
        """接管共享连接和启用发布确认的 Channel。"""

        self._connection = connection
        self._channel = channel
        self._declared: set[str] = set()
        self._lock = asyncio.Lock()

    @classmethod
    async def create(cls, settings: RabbitMQQueueSettings) -> RabbitBackend:
        """建立开启发布确认和退回错误的 RabbitMQ 连接。"""

        connection = await aio_pika.connect(
            host=settings.host,
            port=settings.port,
            login=settings.username,
            password=settings.password.get_secret_value(),
            virtualhost=settings.virtual_host,
            ssl=settings.ssl,
            timeout=settings.connect_timeout,
        )
        try:
            channel = await connection.channel(publisher_confirms=True, on_return_raises=True)
        except BaseException:
            await connection.close()
            raise
        return cls(connection, channel)

    async def publish(self, queue: str, payload: bytes) -> None:
        """确保持久队列存在后，通过默认 exchange 发布持久消息。"""

        async with self._lock:
            # 声明结果按队列名缓存，避免每次发布都产生一次协议往返。
            if queue not in self._declared:
                await self._channel.declare_queue(queue, durable=True)
                self._declared.add(queue)
        await self._channel.default_exchange.publish(
            aio_pika.Message(body=payload, delivery_mode=aio_pika.DeliveryMode.PERSISTENT, content_type="application/json"),
            routing_key=queue,
            mandatory=True,
        )

    async def consumer(self, queue: str, concurrency: int) -> RabbitConsumer:
        """使用并发数作为 prefetch，限制服务端推送的未确认消息数。"""

        channel = await self._connection.channel()
        try:
            await channel.set_qos(prefetch_count=concurrency)
            source = await channel.declare_queue(queue, durable=True)
            iterator = source.iterator()
            await iterator.__aenter__()
            return RabbitConsumer(channel, iterator)
        except BaseException:
            await channel.close()
            raise

    async def aclose(self) -> None:
        """关闭 RabbitMQ 连接及其所属发布 Channel。"""

        await self._connection.close()
