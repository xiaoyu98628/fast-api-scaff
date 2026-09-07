import asyncio
import signal
from collections.abc import Callable
from functools import partial

from app.bootstrap.build import build_application_container
from app.bootstrap.worker.composition import build_worker_registry
from app.config.settings import Settings
from app.interfaces.worker.executor import JobExecutor
from app.interfaces.worker.registry import HandlerRegistry
from app.interfaces.worker.runner import WorkerRunner
from app.runtime.container import ApplicationContainer
from app.runtime.lifecycle import ApplicationRuntime


class WorkerHost:
    def __init__(
        self,
        settings: Settings,
        *,
        container_builder: Callable[[Settings], ApplicationContainer] = build_application_container,
        registry_builder: Callable[[ApplicationContainer], HandlerRegistry] = build_worker_registry,
    ) -> None:
        self._settings = settings
        self._container_builder = container_builder
        self._registry_builder = registry_builder

    def run(self, *, connection: str | None, queue: str | None, concurrency: int | None) -> None:
        asyncio.run(self.serve(connection=connection, queue=queue, concurrency=concurrency))

    async def serve(self, *, connection: str | None, queue: str | None, concurrency: int | None, stop: asyncio.Event | None = None) -> None:
        active_stop = stop if stop is not None else asyncio.Event()
        loop = asyncio.get_running_loop()
        installed: list[signal.Signals] = []
        if stop is None:
            for signum in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(signum, active_stop.set)
                installed.append(signum)
        try:
            async with ApplicationRuntime(partial(self._container_builder, self._settings)) as container:
                registry = self._registry_builder(container)
                registry.require_handlers()
                name = container.queues.resolve_name(connection)
                target = container.queues.queue_name(name, queue)
                count = self._settings.queue.worker.concurrency if concurrency is None else concurrency
                executor = JobExecutor(name, target, registry, container.queues.failed_jobs, container.queues.codec)
                runner = WorkerRunner(concurrency=count, shutdown_timeout=self._settings.queue.worker.shutdown_timeout_seconds)
                async with container.queues.consume(connection=name, queue=target, concurrency=count) as consumer:
                    await runner.run(consumer, executor, active_stop)
        finally:
            for signum in installed:
                loop.remove_signal_handler(signum)
