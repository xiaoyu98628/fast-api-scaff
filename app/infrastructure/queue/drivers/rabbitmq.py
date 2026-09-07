import asyncio

import aio_pika
from aio_pika.abc import AbstractChannel, AbstractConnection, AbstractIncomingMessage, AbstractQueueIterator

from app.config.queue import RabbitMQQueueSettings
from app.infrastructure.queue.errors import QueueError


class RabbitDelivery:
    def __init__(self, message: AbstractIncomingMessage) -> None:
        self._message = message
        self.payload = message.body
        self.identity = message.message_id or f"delivery:{message.delivery_tag}"

    async def acknowledge(self) -> None:
        await self._message.ack()


class RabbitConsumer:
    def __init__(self, channel: AbstractChannel, iterator: AbstractQueueIterator) -> None:
        self._channel = channel
        self._iterator = iterator
        self._closed = False

    async def receive(self) -> RabbitDelivery:
        if self._closed:
            raise QueueError("RabbitMQ 消费者已关闭")
        return RabbitDelivery(await self._iterator.__anext__())

    async def aclose(self) -> None:
        self._closed = True
        try:
            await self._iterator.close()
        finally:
            await self._channel.close()


class RabbitBackend:
    def __init__(self, connection: AbstractConnection, channel: AbstractChannel) -> None:
        self._connection = connection
        self._channel = channel
        self._declared: set[str] = set()
        self._lock = asyncio.Lock()

    @classmethod
    async def create(cls, settings: RabbitMQQueueSettings) -> RabbitBackend:
        connection = await aio_pika.connect(settings.url.get_secret_value(), timeout=settings.publish_timeout)
        try:
            channel = await connection.channel(publisher_confirms=True, on_return_raises=True)
        except BaseException:
            await connection.close()
            raise
        return cls(connection, channel)

    async def publish(self, queue: str, payload: bytes) -> None:
        async with self._lock:
            if queue not in self._declared:
                await self._channel.declare_queue(queue, durable=True)
                self._declared.add(queue)
        await self._channel.default_exchange.publish(
            aio_pika.Message(body=payload, delivery_mode=aio_pika.DeliveryMode.PERSISTENT, content_type="application/json"),
            routing_key=queue,
            mandatory=True,
        )

    async def consumer(self, queue: str, concurrency: int) -> RabbitConsumer:
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
        await self._connection.close()
