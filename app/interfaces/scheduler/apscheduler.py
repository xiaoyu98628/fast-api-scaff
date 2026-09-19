"""使用 APScheduler 实现项目调度引擎边界。"""

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timedelta

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
        try:
            for definition in definitions:
                self._register(scheduler, definition, dispatcher)
        except Exception as error:
            raise SchedulerConfigurationError("定时计划配置不合法") from error

        try:
            scheduler.start()
        except Exception as error:
            raise SchedulerError("调度引擎启动失败") from error
        self._started = True

    async def wait(self, stop: asyncio.Event) -> None:
        """等待宿主停止请求。"""

        if not self._started:
            raise SchedulerError("调度引擎尚未启动")
        await stop.wait()

    async def aclose(self) -> None:
        """幂等停止 APScheduler，并禁止再次启动。"""

        scheduler = self._scheduler
        started = self._started
        self._scheduler = None
        self._started = False
        self._closed = True

        if scheduler is None or not started:
            return
        try:
            scheduler.shutdown(wait=True)
        except Exception as error:
            raise SchedulerError("调度引擎停止失败") from error

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
    ) -> Callable[[], object]:
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
                start_date = now if trigger.start is IntervalStartPolicy.IMMEDIATELY else now + timedelta(seconds=trigger.seconds)
                return IntervalTrigger(seconds=trigger.seconds, start_date=start_date)


def build_scheduler_engine() -> SchedulerEngine:
    """构建封装 APScheduler 的默认调度引擎。"""

    return ApschedulerEngine()
