"""组装并运行独立队列 Worker 宿主。"""

import asyncio
import signal
from collections.abc import Callable
from functools import partial

from app.bootstrap.build import build_application_container
from app.config.settings import Settings
from app.interfaces.worker.executor import JobExecutor
from app.interfaces.worker.resolver import JobResolver, JobTypeResolver
from app.interfaces.worker.runner import WorkerRunner
from app.runtime.container import ApplicationContainer
from app.runtime.lifecycle import ApplicationRuntime


class WorkerHost:
    """复用应用运行时，在独立进程中消费一个逻辑队列。"""

    def __init__(
        self,
        settings: Settings,
        *,
        container_builder: Callable[[Settings], ApplicationContainer] = build_application_container,
        resolver_builder: Callable[[], JobTypeResolver] = JobResolver,
    ) -> None:
        """保存 Worker 配置以及可替换的容器和任务解析器工厂。"""

        self._settings = settings
        self._container_builder = container_builder
        self._resolver_builder = resolver_builder

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
            async with ApplicationRuntime(partial(self._container_builder, self._settings)) as container:
                # 解析默认值后只订阅一个逻辑队列；命名队列需要独立 Worker。
                resolver = self._resolver_builder()
                name = container.queues.resolve_name(connection)
                target = container.queues.queue_name(name, queue)
                count = self._settings.queue.worker.concurrency if concurrency is None else concurrency
                executor = JobExecutor(name, target, resolver, container.queues.failed_jobs, container.queues.codec)
                runner = WorkerRunner(concurrency=count, shutdown_timeout=self._settings.queue.worker.shutdown_timeout_seconds)
                async with container.queues.consume(connection=name, queue=target, concurrency=count) as consumer:
                    await runner.run(consumer, executor, active_stop)
        finally:
            for signum in installed:
                loop.remove_signal_handler(signum)
