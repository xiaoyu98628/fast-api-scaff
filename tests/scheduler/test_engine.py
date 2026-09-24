"""验证 APScheduler 适配器的映射、投递和生命周期。"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.infrastructure.queue.job import QueueJob
from app.interfaces.scheduler.apscheduler import ApschedulerEngine
from app.interfaces.scheduler.contracts import (
    CoalescePolicy,
    CronSchedule,
    IntervalSchedule,
    IntervalStartPolicy,
    QueueJobSchedule,
)
from app.interfaces.scheduler.errors import SchedulerError
from tests.scheduler.fakes import FakeDispatcher


@dataclass(frozen=True, slots=True)
class ExampleJob(QueueJob[object]):
    value: int

    async def handle(self, context: object) -> None:
        del context


class CapturingScheduler:
    """保存 APScheduler 注册参数并提供可观察生命周期。"""

    def __init__(self) -> None:
        self.jobs: list[tuple[Callable, object, dict[str, object]]] = []
        self.started = False
        self.paused = False
        self.shutdown_wait: bool | None = None
        self.shutdown_listener: Callable[[object], None] | None = None

    def add_executor(self, _executor: object, *, alias: str) -> None:
        assert alias == "default"

    def add_listener(self, callback: Callable[[object], None], _mask: int) -> None:
        self.shutdown_listener = callback

    def add_job(self, callback: Callable, *, trigger: object, **options: object) -> None:
        self.jobs.append((callback, trigger, options))

    def start(self) -> None:
        self.started = True

    def pause(self) -> None:
        self.paused = True

    def shutdown(self, *, wait: bool) -> None:
        self.shutdown_wait = wait
        assert self.shutdown_listener is not None
        self.shutdown_listener(object())


def _engine(fake: CapturingScheduler, *, now: datetime | None = None) -> ApschedulerEngine:
    clock = (lambda: now) if now is not None else (lambda: datetime.now().astimezone())
    return ApschedulerEngine(
        scheduler_factory=lambda: cast(AsyncIOScheduler, fake),
        clock=cast(Callable[[], datetime], clock),
    )


@pytest.mark.asyncio
async def test_engine_maps_cron_and_dispatches_existing_queue_job(caplog: pytest.LogCaptureFixture) -> None:
    fake = CapturingScheduler()
    dispatcher = FakeDispatcher()
    job = ExampleJob(7)
    definition = QueueJobSchedule(
        id="example.cron",
        trigger=CronSchedule(hour=3, minute=15, day_of_week="mon-fri"),
        job=job,
        connection="redis",
        queue="maintenance",
        coalesce=CoalescePolicy.LATEST,
        misfire_grace_seconds=90,
    )
    engine = _engine(fake)

    await engine.start((definition,), dispatcher)

    assert fake.started is True
    assert len(fake.jobs) == 1
    callback, trigger, options = fake.jobs[0]
    assert isinstance(trigger, CronTrigger)
    assert trigger.timezone is not None
    assert options == {
        "id": "example.cron",
        "replace_existing": True,
        "coalesce": True,
        "max_instances": 1,
        "misfire_grace_time": 90,
    }

    caplog.set_level(logging.INFO, logger="app.interfaces.scheduler.apscheduler")
    await callback()

    assert dispatcher.calls == [(job, "redis", "maintenance")]
    record = next(record for record in caplog.records if getattr(record, "event", None) == "scheduler.job_dispatched")
    assert getattr(record, "details") == {
        "schedule_id": "example.cron",
        "job_id": str(dispatcher.job_id),
    }

    await engine.aclose()
    assert fake.paused is True
    assert fake.shutdown_wait is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("policy", "expected_start"),
    [
        (IntervalStartPolicy.IMMEDIATELY, datetime(2026, 9, 19, 12, 0, 30, tzinfo=UTC)),
        (IntervalStartPolicy.AFTER_INTERVAL, datetime(2026, 9, 19, 12, 0, 30, tzinfo=UTC)),
    ],
)
async def test_engine_fixes_interval_first_run_semantics(
    policy: IntervalStartPolicy,
    expected_start: datetime,
) -> None:
    now = datetime(2026, 9, 19, 12, tzinfo=UTC)
    fake = CapturingScheduler()
    definition = QueueJobSchedule(
        id=f"example.interval.{policy.value}",
        trigger=IntervalSchedule(seconds=30, start=policy),
        job=ExampleJob(1),
        coalesce=CoalescePolicy.ALL,
    )
    engine = _engine(fake, now=now)
    dispatcher = FakeDispatcher()

    await engine.start((definition,), dispatcher)

    _, trigger, options = fake.jobs[0]
    assert isinstance(trigger, IntervalTrigger)
    assert trigger.start_date == expected_start
    assert options["coalesce"] is False
    assert trigger.interval == timedelta(seconds=30)
    assert dispatcher.calls == ([(definition.job, None, None)] if policy is IntervalStartPolicy.IMMEDIATELY else [])
    await engine.aclose()


@pytest.mark.asyncio
async def test_immediate_interval_dispatches_before_full_period_elapses() -> None:
    """长间隔计划在启动阶段直接投递，不依赖 APScheduler 的首次 misfire。"""

    dispatcher = FakeDispatcher()
    definition = QueueJobSchedule(
        id="example.immediate",
        trigger=IntervalSchedule(seconds=60, start=IntervalStartPolicy.IMMEDIATELY),
        job=ExampleJob(1),
    )
    engine = ApschedulerEngine()

    await asyncio.wait_for(engine.start((definition,), dispatcher), timeout=2)
    try:
        assert dispatcher.calls == [(definition.job, None, None)]
    finally:
        await engine.aclose()


@pytest.mark.asyncio
async def test_immediate_dispatch_failure_still_registers_next_interval(caplog: pytest.LogCaptureFixture) -> None:
    """首次发布失败仍记录诊断，并从该次尝试结束后继续周期计划。"""

    fake = CapturingScheduler()
    definition = QueueJobSchedule(
        id="example.immediate.failure",
        trigger=IntervalSchedule(seconds=30, start=IntervalStartPolicy.IMMEDIATELY),
        job=ExampleJob(1),
    )

    async def fail_dispatch(*_args: object, **_kwargs: object):
        raise RuntimeError("sensitive queue detail")

    caplog.set_level(logging.INFO, logger="app.interfaces.scheduler.apscheduler")
    engine = _engine(fake, now=datetime(2026, 9, 19, 12, tzinfo=UTC))
    await engine.start((definition,), fail_dispatch)

    assert len(fake.jobs) == 1
    assert isinstance(fake.jobs[0][1], IntervalTrigger)
    record = next(record for record in caplog.records if getattr(record, "event", None) == "scheduler.dispatch_failed")
    assert "sensitive queue detail" not in record.getMessage()
    await engine.aclose()


@pytest.mark.asyncio
async def test_shutdown_waits_for_initial_dispatch() -> None:
    """关闭请求到来时，启动阶段的首次投递仍有机会完成。"""

    fake = CapturingScheduler()
    started = asyncio.Event()
    release = asyncio.Event()
    completed = False

    async def dispatch(
        job: object,
        *,
        connection: str | None = None,
        queue: str | None = None,
        correlation_id: str | None = None,
    ) -> UUID:
        nonlocal completed
        del job, connection, queue, correlation_id
        started.set()
        await release.wait()
        completed = True
        return FakeDispatcher().job_id

    definition = QueueJobSchedule(
        id="example.immediate.shutdown",
        trigger=IntervalSchedule(seconds=30, start=IntervalStartPolicy.IMMEDIATELY),
        job=ExampleJob(1),
    )
    engine = _engine(fake)
    starting = asyncio.create_task(engine.start((definition,), dispatch))
    await asyncio.wait_for(started.wait(), timeout=2)
    assert not fake.jobs

    closing = asyncio.create_task(engine.aclose())
    try:
        await asyncio.sleep(0)
        assert not closing.done()
        assert not completed
    finally:
        release.set()
        await asyncio.wait_for(starting, timeout=2)
        await asyncio.wait_for(closing, timeout=2)

    assert completed
    assert not fake.jobs


@pytest.mark.asyncio
async def test_dispatch_failure_is_sanitized_and_does_not_stop_scheduler(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake = CapturingScheduler()
    definition = QueueJobSchedule(
        id="example.failure",
        trigger=CronSchedule(minute="*/5"),
        job=ExampleJob(1),
    )

    async def fail_dispatch(*_args: object, **_kwargs: object):
        raise RuntimeError("sensitive queue detail")

    engine = _engine(fake)
    await engine.start((definition,), fail_dispatch)
    callback, _, _ = fake.jobs[0]
    caplog.set_level(logging.INFO, logger="app.interfaces.scheduler.apscheduler")

    await callback()

    record = next(record for record in caplog.records if getattr(record, "event", None) == "scheduler.dispatch_failed")
    assert getattr(record, "details")["error_type"] == "builtins.RuntimeError"
    assert "sensitive queue detail" not in record.getMessage()
    await engine.aclose()


@pytest.mark.asyncio
async def test_closed_engine_rejects_restart() -> None:
    fake = CapturingScheduler()
    engine = _engine(fake)
    await engine.start((), FakeDispatcher())
    await engine.aclose()

    with pytest.raises(SchedulerError, match="已经关闭"):
        await engine.start((), FakeDispatcher())


@pytest.mark.asyncio
async def test_shutdown_waits_for_inflight_dispatch_before_canceling_executor() -> None:
    """真实 APScheduler 运行中的投递必须先完成，随后才关闭调度器。"""

    started = asyncio.Event()
    release = asyncio.Event()
    completed = asyncio.Event()
    canceled = False

    async def dispatch(
        job: object,
        *,
        connection: str | None = None,
        queue: str | None = None,
        correlation_id: str | None = None,
    ) -> UUID:
        nonlocal canceled
        del job, connection, queue, correlation_id
        started.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            canceled = True
            raise
        completed.set()
        return FakeDispatcher().job_id

    engine = ApschedulerEngine()
    definition = QueueJobSchedule(
        id="example.shutdown",
        trigger=IntervalSchedule(seconds=1, start=IntervalStartPolicy.AFTER_INTERVAL),
        job=ExampleJob(1),
    )
    await engine.start((definition,), dispatch)
    await asyncio.wait_for(started.wait(), timeout=3)

    closing = asyncio.create_task(engine.aclose())
    try:
        await asyncio.sleep(0)
        assert not closing.done()
        assert not completed.is_set()
    finally:
        release.set()
        await asyncio.wait_for(closing, timeout=2)

    assert completed.is_set()
    assert not canceled
