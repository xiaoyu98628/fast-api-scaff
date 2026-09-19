"""组装并运行独立 Scheduler 宿主。"""

import asyncio
import logging
import signal
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial

from app.bootstrap.build import build_application_container
from app.bootstrap.scheduler.logging import SchedulerLogEvent
from app.config.settings import Settings
from app.infrastructure.logging.record import log_extra, safe_exception_details
from app.interfaces.scheduler.apscheduler import build_scheduler_engine
from app.interfaces.scheduler.contracts import QueueJobSchedule
from app.interfaces.scheduler.discovery import discover_schedule_registry
from app.interfaces.scheduler.engine import SchedulerEngine
from app.interfaces.scheduler.registry import ScheduleRegistry
from app.runtime.container import ApplicationContainer
from app.runtime.lifecycle import ApplicationRuntime

type ContainerBuilder = Callable[[Settings], ApplicationContainer]
type RegistryBuilder = Callable[[], ScheduleRegistry]
type EngineBuilder = Callable[[], SchedulerEngine]

_logger = logging.getLogger("app.bootstrap.scheduler.lifecycle")


@dataclass(frozen=True, slots=True)
class SchedulerHost:
    """复用应用运行时，在独立进程中触发已注册的队列任务。"""

    settings: Settings
    container_builder: ContainerBuilder = build_application_container
    registry_builder: RegistryBuilder = discover_schedule_registry
    engine_builder: EngineBuilder = build_scheduler_engine

    def run(self) -> None:
        """从同步进程入口启动 Scheduler 事件循环。"""

        asyncio.run(self.serve())

    async def serve(self, stop: asyncio.Event | None = None) -> None:
        """运行 Scheduler，直到收到停止信号，并按所有权顺序关闭资源。"""

        active_stop = stop if stop is not None else asyncio.Event()
        loop = asyncio.get_running_loop()
        installed = self._install_signal_handlers(loop, active_stop) if stop is None else ()
        runtime = ApplicationRuntime(partial(self.container_builder, self.settings))
        engine: SchedulerEngine | None = None
        operation_error: BaseException | None = None
        _logger.info("Scheduler starting", extra=log_extra(SchedulerLogEvent.STARTING))

        try:
            try:
                engine = self.engine_builder()
                await self._start(runtime, engine)
            except BaseException as error:
                self._log_failure("Scheduler startup failed", SchedulerLogEvent.START_FAILED, error)
                raise

            await engine.wait(active_stop)
        except BaseException as error:
            operation_error = error
        finally:
            close_errors = await self._close(engine, runtime)
            for signum in installed:
                loop.remove_signal_handler(signum)

        self._raise_errors(operation_error, close_errors)

    async def _start(self, runtime: ApplicationRuntime, engine: SchedulerEngine) -> None:
        """启动容器和调度引擎，并在触发前完成目录与路由校验。"""

        container = await runtime.start()
        definitions = self.registry_builder().definitions
        self._validate_queue_routes(container, definitions)
        await engine.start(definitions, container.queues.dispatch)
        _logger.info(
            "Scheduler schedules discovered",
            extra=log_extra(SchedulerLogEvent.SCHEDULES_DISCOVERED, schedule_count=len(definitions)),
        )
        _logger.info("Scheduler started", extra=log_extra(SchedulerLogEvent.STARTED))

    @staticmethod
    def _install_signal_handlers(
        loop: asyncio.AbstractEventLoop,
        stop: asyncio.Event,
    ) -> tuple[signal.Signals, ...]:
        """让独立进程把终止信号转换为协作式停止请求。"""

        installed = (signal.SIGINT, signal.SIGTERM)
        for signum in installed:
            loop.add_signal_handler(signum, stop.set)
        return installed

    @staticmethod
    async def _close(
        engine: SchedulerEngine | None,
        runtime: ApplicationRuntime,
    ) -> tuple[BaseException, ...]:
        """先停止触发，再关闭容器，并保留全部关闭错误。"""

        _logger.info("Scheduler stopping", extra=log_extra(SchedulerLogEvent.STOPPING))
        errors: list[BaseException] = []
        if engine is not None:
            try:
                await engine.aclose()
            except BaseException as error:
                errors.append(error)
        try:
            await runtime.aclose()
        except BaseException as error:
            errors.append(error)

        if errors:
            SchedulerHost._log_failure(
                "Scheduler shutdown failed",
                SchedulerLogEvent.STOP_FAILED,
                BaseExceptionGroup("Scheduler shutdown failed", errors),
            )
        else:
            _logger.info("Scheduler stopped", extra=log_extra(SchedulerLogEvent.STOPPED))
        return tuple(errors)

    @staticmethod
    def _raise_errors(
        operation_error: BaseException | None,
        close_errors: tuple[BaseException, ...],
    ) -> None:
        """在关闭完成后恢复运行错误，并在必要时聚合关闭根因。"""

        if operation_error is not None and close_errors:
            raise BaseExceptionGroup("Scheduler execution and shutdown failed", (operation_error, *close_errors)) from None
        if operation_error is not None:
            raise operation_error
        if close_errors:
            raise BaseExceptionGroup("Scheduler shutdown failed", close_errors) from None

    @staticmethod
    def _log_failure(message: str, event: SchedulerLogEvent, error: BaseException) -> None:
        """记录不包含异常消息和局部变量的生命周期失败。"""

        error_type, stacktrace = safe_exception_details(error)
        _logger.error(message, extra=log_extra(event, error_type=error_type, stacktrace=stacktrace))

    @staticmethod
    def _validate_queue_routes(
        container: ApplicationContainer,
        definitions: tuple[QueueJobSchedule, ...],
    ) -> None:
        """在启动触发循环前校验全部命名连接和逻辑队列。"""

        for definition in definitions:
            container.queues.queue_name(definition.connection, definition.queue)
