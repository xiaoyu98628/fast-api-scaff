"""验证 APScheduler 适配器的映射、投递和生命周期。"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast

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
        self.shutdown_wait: bool | None = None

    def add_job(self, callback: Callable, *, trigger: object, **options: object) -> None:
        self.jobs.append((callback, trigger, options))

    def start(self) -> None:
        self.started = True

    def shutdown(self, *, wait: bool) -> None:
        self.shutdown_wait = wait


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
    assert fake.shutdown_wait is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("policy", "expected_start"),
    [
        (IntervalStartPolicy.IMMEDIATELY, datetime(2026, 9, 19, 12, tzinfo=UTC)),
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

    await engine.start((definition,), FakeDispatcher())

    _, trigger, options = fake.jobs[0]
    assert isinstance(trigger, IntervalTrigger)
    assert trigger.start_date == expected_start
    assert options["coalesce"] is False
    assert trigger.interval == timedelta(seconds=30)
    await engine.aclose()


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
