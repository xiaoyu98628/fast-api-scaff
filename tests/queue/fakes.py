"""提供队列与 Worker 测试使用的可控替身。"""

from __future__ import annotations

import asyncio
import builtins
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import ClassVar
from uuid import UUID, uuid4

from app.config.database import DatabaseSettings
from app.config.queue import QueueConnection, QueueSettings
from app.infrastructure.database.manager import DatabaseManager
from app.infrastructure.queue.contracts.failed_store import FailedJobRecord
from app.infrastructure.queue.contracts.provider import QueueBackend
from app.infrastructure.queue.errors import QueueError
from app.infrastructure.queue.job import QueueJob
from app.infrastructure.queue.manager import QueueManager


class Codec:
    def encode(self, job: Job) -> bytes:
        return str(job.value).encode()

    def decode(self, payload: bytes) -> Job:
        return Job(int(payload))


@dataclass(frozen=True)
class Job(QueueJob[object]):
    value: int
    codec: ClassVar[Codec] = Codec()

    async def handle(self, context: object) -> None:
        pass


class RecordingFailedJobStore:
    def __init__(self) -> None:
        self._records: dict[UUID, FailedJobRecord] = {}

    async def save(self, record: FailedJobRecord) -> None:
        self._records.setdefault(record.failure_id, record)

    async def find(self, failure_id: UUID) -> FailedJobRecord | None:
        return self._records.get(failure_id)

    async def list(self, *, limit: int = 20, offset: int = 0) -> builtins.list[FailedJobRecord]:
        if limit < 1 or offset < 0:
            raise ValueError("分页参数不合法")
        records = sorted(self._records.values(), key=lambda item: (item.failed_at, item.failure_id), reverse=True)
        return records[offset : offset + limit]

    async def delete(self, failure_id: UUID) -> None:
        self._records.pop(failure_id, None)


class FakeDelivery:
    def __init__(self, payload: bytes, *, identity: str | None = None, consumer: FakeQueueConsumer | None = None) -> None:
        self.payload = payload
        self.identity = str(uuid4()) if identity is None else identity
        self._consumer = consumer
        self.settled = False

    async def acknowledge(self) -> None:
        if self.settled:
            raise QueueError("测试消息已经确认")
        if self._consumer is not None:
            self._consumer.acknowledge(self)
        self.settled = True


class FakeQueueBuffer:
    def __init__(self) -> None:
        self.messages: asyncio.Queue[tuple[str, bytes]] = asyncio.Queue()
        self.recovered: deque[tuple[str, bytes]] = deque()
        self.changed = asyncio.Event()
        self.closed = False

    async def put(self, payload: bytes) -> None:
        if self.closed:
            raise QueueError("测试队列后端已关闭")
        self.messages.put_nowait((str(uuid4()), payload))
        self.changed.set()

    async def take(self, consumer: FakeQueueConsumer) -> tuple[str, bytes]:
        while True:
            if self.closed or consumer.closed:
                raise QueueError("测试消费者已关闭")
            if self.recovered:
                return self.recovered.popleft()
            if not self.messages.empty():
                return self.messages.get_nowait()
            self.changed.clear()
            await self.changed.wait()


class FakeQueueConsumer:
    def __init__(self, buffer: FakeQueueBuffer) -> None:
        self.buffer = buffer
        self.pending: dict[str, FakeDelivery] = {}
        self.closed = False

    async def receive(self) -> FakeDelivery:
        identity, payload = await self.buffer.take(self)
        delivery = FakeDelivery(payload, identity=identity, consumer=self)
        self.pending[identity] = delivery
        return delivery

    def acknowledge(self, delivery: FakeDelivery) -> None:
        if self.closed or self.buffer.closed or delivery.identity not in self.pending:
            raise QueueError("测试消息不可确认")
        self.pending.pop(delivery.identity)

    async def aclose(self) -> None:
        if self.closed:
            return
        self.closed = True
        for delivery in self.pending.values():
            self.buffer.recovered.append((delivery.identity, delivery.payload))
        self.pending.clear()
        self.buffer.changed.set()


class FakeQueueBackend:
    def __init__(self) -> None:
        self._queues: dict[str, FakeQueueBuffer] = {}
        self._closed = False

    def _queue(self, name: str) -> FakeQueueBuffer:
        if self._closed:
            raise QueueError("测试队列后端已关闭")
        return self._queues.setdefault(name, FakeQueueBuffer())

    async def publish(self, queue: str, payload: bytes) -> None:
        await self._queue(queue).put(payload)

    async def consumer(self, queue: str, concurrency: int) -> FakeQueueConsumer:
        return FakeQueueConsumer(self._queue(queue))

    async def aclose(self) -> None:
        self._closed = True
        for buffer in self._queues.values():
            buffer.closed = True
            buffer.changed.set()


def queue_backend_factory(backend: FakeQueueBackend) -> Callable[[QueueConnection], Awaitable[QueueBackend]]:
    async def create(_settings: QueueConnection) -> QueueBackend:
        return backend

    return create


def create_queue_manager() -> QueueManager:
    settings = QueueSettings(
        _env_file=None,
        default="main",
        connections={"main": {"driver": "redis", "host": "localhost"}},
    )
    backend = FakeQueueBackend()
    return QueueManager(
        settings,
        DatabaseManager(DatabaseSettings(_env_file=None)),
        failed_jobs=RecordingFailedJobStore(),
        factory=queue_backend_factory(backend),
    )
