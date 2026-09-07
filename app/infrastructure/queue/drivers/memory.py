import asyncio
from collections import deque
from dataclasses import dataclass, field
from uuid import uuid4

from app.infrastructure.queue.errors import QueueError


@dataclass(slots=True)
class MemoryBuffer:
    capacity: int
    messages: asyncio.Queue[tuple[str, bytes]] = field(default_factory=asyncio.Queue)
    recovered: deque[tuple[str, bytes]] = field(default_factory=deque)
    changed: asyncio.Event = field(default_factory=asyncio.Event)
    outstanding: int = 0
    closed: bool = False

    async def put(self, payload: bytes) -> None:
        while self.outstanding >= self.capacity and not self.closed:
            self.changed.clear()
            await self.changed.wait()
        if self.closed:
            raise QueueError("内存连接已关闭")
        self.outstanding += 1
        self.messages.put_nowait((str(uuid4()), payload))
        self.changed.set()

    async def take(self, consumer: MemoryConsumer) -> tuple[str, bytes]:
        while True:
            if self.closed or consumer.closed:
                raise QueueError("内存消费者已关闭")
            if self.recovered:
                return self.recovered.popleft()
            if not self.messages.empty():
                item = self.messages.get_nowait()
                self.messages.task_done()
                return item
            self.changed.clear()
            await self.changed.wait()


class MemoryDelivery:
    def __init__(self, consumer: MemoryConsumer, identity: str, payload: bytes) -> None:
        self.consumer = consumer
        self.identity = identity
        self.payload = payload
        self.settled = False

    async def acknowledge(self) -> None:
        if self.settled or self.consumer.closed or self.consumer.buffer.closed:
            raise QueueError("消息已确认或消费者已关闭")
        self.settled = True
        self.consumer.pending.pop(self.identity)
        self.consumer.buffer.outstanding -= 1
        self.consumer.buffer.changed.set()


class MemoryConsumer:
    def __init__(self, buffer: MemoryBuffer) -> None:
        self.buffer = buffer
        self.pending: dict[str, MemoryDelivery] = {}
        self.closed = False

    async def receive(self) -> MemoryDelivery:
        identity, payload = await self.buffer.take(self)
        delivery = MemoryDelivery(self, identity, payload)
        self.pending[identity] = delivery
        return delivery

    async def aclose(self) -> None:
        if self.closed:
            return
        self.closed = True
        for delivery in self.pending.values():
            self.buffer.recovered.append((delivery.identity, delivery.payload))
        self.pending.clear()
        self.buffer.changed.set()


class MemoryBackend:
    def __init__(self, capacity: int) -> None:
        self._capacity = capacity
        self._buffers: dict[str, MemoryBuffer] = {}
        self._closed = False

    def _buffer(self, queue: str) -> MemoryBuffer:
        if self._closed:
            raise QueueError("内存连接已关闭")
        return self._buffers.setdefault(queue, MemoryBuffer(self._capacity))

    async def publish(self, queue: str, payload: bytes) -> None:
        await self._buffer(queue).put(payload)

    async def consumer(self, queue: str, concurrency: int) -> MemoryConsumer:
        return MemoryConsumer(self._buffer(queue))

    async def aclose(self) -> None:
        self._closed = True
        for buffer in self._buffers.values():
            buffer.closed = True
            buffer.changed.set()
