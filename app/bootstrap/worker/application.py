"""组装并运行独立队列 Worker 宿主。"""

import asyncio
import logging
import signal
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial

from app.bootstrap.build import build_application_container
from app.bootstrap.worker.logging import WorkerLogEvent
from app.config.settings import Settings
from app.infrastructure.logging.record import log_extra
from app.interfaces.worker.context import WorkerContext
from app.interfaces.worker.executor import JobExecutor
from app.interfaces.worker.resolver import JobResolver, JobTypeResolver
from app.interfaces.worker.runner import WorkerRunner
from app.runtime.container import ApplicationContainer
from app.runtime.lifecycle import ApplicationRuntime

type ContainerBuilder = Callable[[Settings], ApplicationContainer]
type ResolverBuilder = Callable[[], JobTypeResolver]

_logger = logging.getLogger("app.bootstrap.worker.lifecycle")


@dataclass(frozen=True, slots=True)
class WorkerHost:
    """复用应用运行时，在独立进程中消费一个逻辑队列。"""

    settings: Settings
    container_builder: ContainerBuilder = build_application_container
    resolver_builder: ResolverBuilder = JobResolver

    def run(self, *, connection: str | None, queue: str | None, concurrency: int | None) -> None:
        """从同步进程入口启动 Worker 事件循环。"""

        asyncio.run(self.serve(connection=connection, queue=queue, concurrency=concurrency))

    async def serve(self, *, connection: str | None, queue: str | None, concurrency: int | None, stop: asyncio.Event | None = None) -> None:
        """消费任务直到收到停止信号，并由运行时统一释放资源。"""

        active_stop = stop if stop is not None else asyncio.Event()
        loop = asyncio.get_running_loop()
        installed: list[signal.Signals] = []
        # 嵌入式调用和测试可以注入停止事件；只有独立进程才接管系统信号。
        if stop is None:
            for signum in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(signum, active_stop.set)
                installed.append(signum)
        try:
            runtime = ApplicationRuntime(partial(self.container_builder, self.settings))
            _logger.info("Worker starting", extra=log_extra(WorkerLogEvent.STARTING))
            try:
                try:
                    container = await runtime.start()
                except Exception:
                    _logger.exception(
                        "Worker startup failed",
                        extra=log_extra(WorkerLogEvent.START_FAILED),
                    )
                    raise

                _logger.info("Worker started", extra=log_extra(WorkerLogEvent.STARTED))
                context = WorkerContext(settings=self.settings, container=container)
                await self._consume(
                    context,
                    connection=connection,
                    queue=queue,
                    concurrency=concurrency,
                    stop=active_stop,
                )
            finally:
                _logger.info("Worker stopping", extra=log_extra(WorkerLogEvent.STOPPING))
                try:
                    await runtime.aclose()
                except Exception:
                    _logger.exception(
                        "Worker shutdown failed",
                        extra=log_extra(WorkerLogEvent.STOP_FAILED),
                    )
                    raise
                _logger.info("Worker stopped", extra=log_extra(WorkerLogEvent.STOPPED))
        finally:
            for signum in installed:
                loop.remove_signal_handler(signum)

    async def _consume(
        self,
        context: WorkerContext,
        *,
        connection: str | None,
        queue: str | None,
        concurrency: int | None,
        stop: asyncio.Event,
    ) -> None:
        """在已经启动的应用上下文中装配并运行队列消费者。"""

        container = context.container
        # 解析默认值后只订阅一个逻辑队列；命名队列需要独立 Worker。
        name = container.queues.resolve_name(connection)
        target = container.queues.queue_name(name, queue)
        count = self.settings.queue.worker.concurrency if concurrency is None else concurrency
        resolver = self.resolver_builder()
        executor = JobExecutor(name, target, resolver, container.queues.failed_jobs, container.queues.codec, context)
        runner = WorkerRunner(concurrency=count, shutdown_timeout=self.settings.queue.worker.shutdown_timeout_seconds)
        async with container.queues.consume(connection=name, queue=target, concurrency=count) as consumer:
            await runner.run(consumer, executor, stop)
