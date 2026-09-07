from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime
from functools import partial
from uuid import UUID, uuid4

from anyio import CancelScope
from pydantic import ValidationError

from app.config.queue import QueueConnection, QueueSettings, parse_connection
from app.infrastructure.database.manager import DatabaseManager
from app.infrastructure.queue.catalog import JobCatalog
from app.infrastructure.queue.codecs.envelope_json import EnvelopeJsonCodec
from app.infrastructure.queue.contracts.consumer import QueueConsumer
from app.infrastructure.queue.contracts.failed_store import FailedJobStore
from app.infrastructure.queue.contracts.provider import QueueBackend
from app.infrastructure.queue.dispatcher import Dispatcher
from app.infrastructure.queue.errors import QueueConfigurationError, QueueError
from app.infrastructure.queue.failed.memory import MemoryFailedJobStore
from app.infrastructure.queue.failed.sql.store import SqlFailedJobStore
from app.infrastructure.queue.providers.registry import create_backend
from app.infrastructure.queue.resource import close_backend
from app.infrastructure.resources.lazy import AsyncLazy

type BackendFactory = Callable[[QueueConnection], Awaitable[QueueBackend]]


class QueueManager:
    def __init__(
        self, settings: QueueSettings, databases: DatabaseManager, *, catalog: JobCatalog | None = None, factory: BackendFactory = create_backend
    ) -> None:
        self.catalog = catalog if catalog is not None else JobCatalog()
        self.codec = EnvelopeJsonCodec(settings.max_message_bytes)
        self._default = settings.default
        self._closed = False
        self._consumers: list[QueueConsumer] = []
        self._configs = self._validate(settings)
        self._resources = {name: AsyncLazy(partial(factory, config), close_backend) for name, config in self._configs.items()}
        self.failed_jobs: FailedJobStore = (
            SqlFailedJobStore(databases, settings.failed.database) if settings.failed.driver == "sql" else MemoryFailedJobStore()
        )
        self.persistent_failures = settings.failed.driver == "sql"

    @staticmethod
    def _validate(settings: QueueSettings) -> dict[str, QueueConnection]:
        if settings.default is not None and settings.default not in settings.connections:
            raise QueueConfigurationError("默认队列连接未配置")
        configs: dict[str, QueueConnection] = {}
        for name, raw in settings.connections.items():
            if not name.strip() or len(name) > 200:
                raise QueueConfigurationError("队列连接名不合法")
            try:
                configs[name] = parse_connection(raw)
            except ValidationError:
                raise QueueConfigurationError(f"队列连接 {name!r} 配置不合法") from None
        return configs

    def resolve_name(self, name: str | None = None) -> str:
        if self._closed:
            raise QueueError("队列管理器已关闭")
        resolved = self._default if name is None else name
        if resolved is None or resolved not in self._resources:
            raise QueueConfigurationError("队列连接未配置")
        return resolved

    def is_initialized(self, name: str | None = None) -> bool:
        return self._resources[self.resolve_name(name)].initialized

    async def get(self, name: str | None = None) -> Dispatcher:
        resolved = self.resolve_name(name)
        backend = await self._resources[resolved].get()
        config = self._configs[resolved]
        return Dispatcher(backend, self.catalog, self.codec, config.default_queue, config.publish_timeout)

    @asynccontextmanager
    async def consume(self, *, connection: str | None = None, queue: str | None = None, concurrency: int = 1) -> AsyncIterator[QueueConsumer]:
        resolved = self.resolve_name(connection)
        target = self._configs[resolved].default_queue if queue is None else queue
        if not target.strip() or len(target) > 200 or concurrency < 1:
            raise QueueConfigurationError("消费参数不合法")
        backend = await self._resources[resolved].get()
        consumer = await backend.consumer(target, concurrency)
        if self._closed:
            await consumer.aclose()
            raise QueueError("队列管理器已关闭")
        self._consumers.append(consumer)
        try:
            yield consumer
        finally:
            with CancelScope(shield=True):
                try:
                    await consumer.aclose()
                finally:
                    if consumer in self._consumers:
                        self._consumers.remove(consumer)

    def queue_name(self, connection: str | None = None, queue: str | None = None) -> str:
        config = self._configs[self.resolve_name(connection)]
        return config.default_queue if queue is None else queue

    async def replay(self, failure_id: UUID) -> UUID:
        record = await self.failed_jobs.find(failure_id)
        if record is None:
            raise QueueError("失败记录不存在")
        message = self.codec.decode(record.payload)
        replay = replace(message, job_id=uuid4(), enqueued_at=datetime.now(), replay_of=record.failure_id)
        dispatcher = await self.get(record.connection)
        await dispatcher.publish_envelope(replay, queue=record.queue)
        return replay.job_id

    async def aclose(self) -> None:
        self._closed = True
        for resource in self._resources.values():
            resource.begin_close()
        errors: list[BaseException] = []
        with CancelScope(shield=True):
            for consumer in reversed(tuple(self._consumers)):
                try:
                    await consumer.aclose()
                except BaseException as error:
                    errors.append(error)
            self._consumers.clear()
            for resource in reversed(tuple(self._resources.values())):
                try:
                    await resource.aclose()
                except BaseException as error:
                    errors.append(error)
        if errors:
            raise BaseExceptionGroup("队列资源关闭失败", errors)
