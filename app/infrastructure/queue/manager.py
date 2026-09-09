"""管理命名队列连接、延迟资源、消费者和失败任务重放。"""

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
from app.infrastructure.queue.codecs.envelope_json import EnvelopeJsonCodec
from app.infrastructure.queue.contracts.consumer import QueueConsumer
from app.infrastructure.queue.contracts.failed_store import FailedJobStore
from app.infrastructure.queue.contracts.provider import QueueBackend
from app.infrastructure.queue.dispatcher import Dispatcher
from app.infrastructure.queue.errors import QueueConfigurationError, QueueError
from app.infrastructure.queue.failed.sql.store import SqlFailedJobStore
from app.infrastructure.queue.providers.registry import create_backend
from app.infrastructure.queue.resource import close_backend
from app.infrastructure.resources.lazy import AsyncLazy

type BackendFactory = Callable[[QueueConnection], Awaitable[QueueBackend]]


class QueueManager:
    """提供宿主层使用的队列统一入口和一次性资源生命周期。"""

    def __init__(
        self,
        settings: QueueSettings,
        databases: DatabaseManager,
        *,
        failed_jobs: FailedJobStore | None = None,
        factory: BackendFactory = create_backend,
    ) -> None:
        """校验连接配置，并建立后端和失败存储的延迟生命周期。"""

        self.codec = EnvelopeJsonCodec(settings.max_message_bytes)
        self._default = settings.default
        self._closed = False
        self._consumers: list[QueueConsumer] = []
        self._configs = self._validate(settings)
        self._resources = {name: AsyncLazy(partial(factory, config), close_backend) for name, config in self._configs.items()}
        self._databases = databases
        self._failed_database = settings.failed.database
        self._failed_jobs = failed_jobs

    @property
    def failed_jobs(self) -> FailedJobStore:
        """首次使用时创建 SQL 失败存储，并校验目标数据库。"""

        # 失败存储保持延迟创建，使不使用队列的 HTTP/Console 启动不依赖数据库。
        if self._failed_jobs is None:
            if not self._failed_database.strip() or self._failed_database not in self._databases.connection_names:
                raise QueueConfigurationError("队列 SQL 失败存储数据库未配置")
            self._failed_jobs = SqlFailedJobStore(self._databases, self._failed_database)
        return self._failed_jobs

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
        """解析默认或显式连接名，并拒绝关闭后的资源获取。"""

        self._ensure_open()
        resolved = self._default if name is None else name
        if resolved is None or resolved not in self._resources:
            raise QueueConfigurationError("队列连接未配置")
        return resolved

    def _ensure_open(self) -> None:
        if self._closed:
            raise QueueError("队列管理器已关闭")

    def is_initialized(self, name: str | None = None) -> bool:
        """报告指定后端是否已经被实际创建。"""

        return self._resources[self.resolve_name(name)].initialized

    async def get(self, name: str | None = None) -> Dispatcher:
        """延迟获取连接后端并构造生命周期受控的 Dispatcher。"""

        resolved = self.resolve_name(name)
        backend = await self._resources[resolved].get()
        config = self._configs[resolved]
        return Dispatcher(backend, self.codec, config.default_queue, config.publish_timeout, ensure_active=self._ensure_open)

    async def dispatch(
        self,
        job: object,
        *,
        connection: str | None = None,
        queue: str | None = None,
        correlation_id: str | None = None,
    ) -> UUID:
        """通过默认或指定连接投递一个 QueueJob。"""

        dispatcher = await self.get(connection)
        return await dispatcher.dispatch(job, queue=queue, correlation_id=correlation_id)

    @asynccontextmanager
    async def consume(self, *, connection: str | None = None, queue: str | None = None, concurrency: int = 1) -> AsyncIterator[QueueConsumer]:
        """创建并登记消费者，退出上下文时保证释放消费资源。"""

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
            # 屏蔽外部取消，确保后端有机会恢复尚未确认的消息。
            with CancelScope(shield=True):
                try:
                    await consumer.aclose()
                finally:
                    if consumer in self._consumers:
                        self._consumers.remove(consumer)

    def queue_name(self, connection: str | None = None, queue: str | None = None) -> str:
        """解析一个连接最终使用的逻辑队列名。"""

        config = self._configs[self.resolve_name(connection)]
        return config.default_queue if queue is None else queue

    async def replay(self, failure_id: UUID) -> UUID:
        """用新 job_id 重发原始信封，并保留 replay_of 追踪关系。"""

        record = await self.failed_jobs.find(failure_id)
        if record is None:
            raise QueueError("失败记录不存在")
        message = self.codec.decode(record.payload)
        replay = replace(message, job_id=uuid4(), enqueued_at=datetime.now(), replay_of=record.failure_id)
        dispatcher = await self.get(record.connection)
        await dispatcher.publish_envelope(replay, queue=record.queue)
        return replay.job_id

    async def aclose(self) -> None:
        """先停止获取，再关闭消费者和后端，并聚合全部关闭错误。"""

        self._closed = True
        # 同步封锁所有延迟资源，避免关闭期间有新初始化结果逃逸给调用方。
        for resource in self._resources.values():
            resource.begin_close()
        errors: list[BaseException] = []
        with CancelScope(shield=True):
            # 消费者先关闭，确保不再使用随后释放的共享后端。
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
