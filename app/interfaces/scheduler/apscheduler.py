"""使用 APScheduler 实现项目调度引擎边界。"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

from apscheduler.events import EVENT_SCHEDULER_SHUTDOWN
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.infrastructure.logging.record import log_extra, safe_exception_details
from app.interfaces.scheduler.contracts import (
    CoalescePolicy,
    CronSchedule,
    IntervalSchedule,
    IntervalStartPolicy,
    JobDispatcher,
    QueueJobSchedule,
    ScheduleTrigger,
)
from app.interfaces.scheduler.engine import SchedulerEngine
from app.interfaces.scheduler.errors import SchedulerConfigurationError, SchedulerError

type SchedulerFactory = Callable[[], AsyncIOScheduler]
type LocalClock = Callable[[], datetime]

_logger = logging.getLogger(__name__)


def _local_now() -> datetime:
    """返回带容器操作系统本地 offset 的当前时间。"""

    return datetime.now().astimezone()


class _DrainingAsyncIOExecutor(AsyncIOExecutor):
    """在 Scheduler 关闭前等待已经提交的异步投递结束。"""

    async def drain(self) -> None:
        """等待执行器持有的全部任务，不由关闭流程取消正在发布的消息。"""

        # APScheduler 3 的 shutdown(wait=True) 仍会取消这些 Future，
        # 因此必须在调用 shutdown 前完成等待。
        while pending := getattr(self, "_pending_futures", ()):
            await asyncio.gather(*tuple(pending), return_exceptions=True)


class ApschedulerEngine:
    """把项目计划转换为 APScheduler Trigger 并投递 QueueJob。"""

    def __init__(
        self,
        *,
        scheduler_factory: SchedulerFactory = AsyncIOScheduler,
        clock: LocalClock = _local_now,
    ) -> None:
        """保存可替换的调度器工厂和本地时间源。"""

        self._scheduler_factory = scheduler_factory
        self._clock = clock
        self._scheduler: AsyncIOScheduler | None = None
        self._executor: _DrainingAsyncIOExecutor | None = None
        self._shutdown_event: asyncio.Event | None = None
        self._initial_dispatches: set[asyncio.Task[None]] = set()
        self._started = False
        self._closed = False

    async def start(
        self,
        definitions: tuple[QueueJobSchedule, ...],
        dispatcher: JobDispatcher,
    ) -> None:
        """注册全部代码计划，并启动 APScheduler 触发循环。"""

        if self._closed:
            raise SchedulerError("调度引擎已经关闭")
        if self._scheduler is not None:
            raise SchedulerError("调度引擎已经启动")

        scheduler = self._scheduler_factory()
        self._scheduler = scheduler
        executor = _DrainingAsyncIOExecutor()
        shutdown_event = asyncio.Event()
        self._executor = executor
        self._shutdown_event = shutdown_event
        immediate: list[QueueJobSchedule] = []
        try:
            scheduler.add_executor(executor, alias="default")
            scheduler.add_listener(lambda _event: shutdown_event.set(), EVENT_SCHEDULER_SHUTDOWN)
            for definition in definitions:
                if self._starts_immediately(definition):
                    # 首次投递不交给 APScheduler 的 misfire 窗口，先验证时钟契约。
                    self._build_trigger(definition.trigger)
                    immediate.append(definition)
                else:
                    self._register(scheduler, definition, dispatcher)
        except Exception as error:
            raise SchedulerConfigurationError("定时计划配置不合法") from error

        try:
            scheduler.start()
        except Exception as error:
            raise SchedulerError("调度引擎启动失败") from error
        self._started = True
        await self._start_initial_dispatches(scheduler, tuple(immediate), dispatcher)

    async def _start_initial_dispatches(
        self,
        scheduler: AsyncIOScheduler,
        definitions: tuple[QueueJobSchedule, ...],
        dispatcher: JobDispatcher,
    ) -> None:
        """并发完成首次投递，并让各周期从自己的投递结束时起算。"""

        tasks = tuple(asyncio.create_task(self._dispatch_initial_then_register(scheduler, definition, dispatcher)) for definition in definitions)
        self._initial_dispatches.update(tasks)
        for task in tasks:
            task.add_done_callback(self._initial_dispatches.discard)
        if tasks:
            outcomes = await asyncio.shield(asyncio.gather(*tasks, return_exceptions=True))
            for outcome in outcomes:
                if isinstance(outcome, BaseException):
                    raise SchedulerConfigurationError("首次投递后的定时计划注册失败") from outcome

    async def wait(self, stop: asyncio.Event) -> None:
        """等待宿主停止请求。"""

        if not self._started:
            raise SchedulerError("调度引擎尚未启动")
        await stop.wait()

    async def aclose(self) -> None:
        """幂等停止 APScheduler，并禁止再次启动。"""

        scheduler = self._scheduler
        executor = self._executor
        shutdown_event = self._shutdown_event
        started = self._started
        self._scheduler = None
        self._executor = None
        self._shutdown_event = None
        self._started = False
        self._closed = True

        if scheduler is None or not started:
            return
        try:
            # pause 同步阻止新提交；执行器排空后才能关闭共享队列资源。
            scheduler.pause()
            if self._initial_dispatches:
                await asyncio.gather(*tuple(self._initial_dispatches), return_exceptions=True)
            if executor is not None:
                await executor.drain()
            scheduler.shutdown(wait=False)
            if shutdown_event is not None:
                await shutdown_event.wait()
        except Exception as error:
            raise SchedulerError("调度引擎停止失败") from error

    @staticmethod
    def _starts_immediately(definition: QueueJobSchedule) -> bool:
        """标识需要在启动阶段显式投递一次的 Interval 计划。"""

        return isinstance(definition.trigger, IntervalSchedule) and definition.trigger.start is IntervalStartPolicy.IMMEDIATELY

    async def _dispatch_initial_then_register(
        self,
        scheduler: AsyncIOScheduler,
        definition: QueueJobSchedule,
        dispatcher: JobDispatcher,
    ) -> None:
        """先尝试首次投递，再从完成时刻开始计算后续间隔。"""

        await self._build_callback(definition, dispatcher)()
        if not self._closed:
            self._register(scheduler, definition, dispatcher)

    def _register(
        self,
        scheduler: AsyncIOScheduler,
        definition: QueueJobSchedule,
        dispatcher: JobDispatcher,
    ) -> None:
        """注册一个仅负责向现有队列投递消息的计划。"""

        scheduler.add_job(
            self._build_callback(definition, dispatcher),
            trigger=self._build_trigger(definition.trigger),
            id=definition.id,
            replace_existing=True,
            coalesce=definition.coalesce is CoalescePolicy.LATEST,
            max_instances=1,
            misfire_grace_time=definition.misfire_grace_seconds,
        )

    def _build_callback(
        self,
        definition: QueueJobSchedule,
        dispatcher: JobDispatcher,
    ) -> Callable[[], Awaitable[None]]:
        """创建记录投递结果且不承担业务处理的异步回调。"""

        async def dispatch() -> None:
            try:
                job_id = await dispatcher(
                    definition.job,
                    connection=definition.connection,
                    queue=definition.queue,
                )
            except asyncio.CancelledError:
                raise
            except Exception as error:
                error_type, stacktrace = safe_exception_details(error)
                _logger.error(
                    "Scheduled job dispatch failed",
                    extra=log_extra(
                        "scheduler.dispatch_failed",
                        schedule_id=definition.id,
                        error_type=error_type,
                        stacktrace=stacktrace,
                    ),
                )
                return

            _logger.info(
                "Scheduled job dispatched",
                extra=log_extra(
                    "scheduler.job_dispatched",
                    schedule_id=definition.id,
                    job_id=str(job_id),
                ),
            )

        return dispatch

    def _build_trigger(self, trigger: ScheduleTrigger) -> CronTrigger | IntervalTrigger:
        """映射项目 Trigger，并显式固定 Interval 的首次触发时间。"""

        match trigger:
            case CronSchedule():
                # 不传 timezone，使 Cron 使用 Scheduler 容器的操作系统本地时区。
                return CronTrigger(
                    second=trigger.second,
                    minute=trigger.minute,
                    hour=trigger.hour,
                    day=trigger.day,
                    month=trigger.month,
                    day_of_week=trigger.day_of_week,
                )
            case IntervalSchedule():
                now = self._clock()
                if now.tzinfo is None or now.utcoffset() is None:
                    raise ValueError("Scheduler 本地时钟必须包含 UTC offset")
                # IMMEDIATELY 的首次投递由启动流程显式完成，这里只注册后续周期。
                start_date = now + timedelta(seconds=trigger.seconds)
                return IntervalTrigger(seconds=trigger.seconds, start_date=start_date)


def build_scheduler_engine() -> SchedulerEngine:
    """构建封装 APScheduler 的默认调度引擎。"""

    return ApschedulerEngine()
