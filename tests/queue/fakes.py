import asyncio
import builtins
from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

from app.config.queue import QueueConnection
from app.infrastructure.queue.contracts.failed_store import FailedJobRecord
from app.infrastructure.queue.contracts.provider import QueueBackend
from app.infrastructure.queue.errors import QueueError


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
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.identity = str(uuid4())
        self.settled = False

    async def acknowledge(self) -> None:
        if self.settled:
            raise QueueError("测试消息已经确认")
        self.settled = True


class FakeQueueConsumer:
    def __init__(self, messages: asyncio.Queue[bytes]) -> None:
        self._messages = messages
        self._closed = False

    async def receive(self) -> FakeDelivery:
        if self._closed:
            raise QueueError("测试消费者已关闭")
        return FakeDelivery(await self._messages.get())

    async def aclose(self) -> None:
        self._closed = True


class FakeQueueBackend:
    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue[bytes]] = {}
        self._closed = False

    def _queue(self, name: str) -> asyncio.Queue[bytes]:
        if self._closed:
            raise QueueError("测试队列后端已关闭")
        return self._queues.setdefault(name, asyncio.Queue())

    async def publish(self, queue: str, payload: bytes) -> None:
        await self._queue(queue).put(payload)

    async def consumer(self, queue: str, concurrency: int) -> FakeQueueConsumer:
        return FakeQueueConsumer(self._queue(queue))

    async def aclose(self) -> None:
        self._closed = True


def queue_backend_factory(backend: FakeQueueBackend) -> Callable[[QueueConnection], Awaitable[QueueBackend]]:
    async def create(_settings: QueueConnection) -> QueueBackend:
        return backend

    return create
