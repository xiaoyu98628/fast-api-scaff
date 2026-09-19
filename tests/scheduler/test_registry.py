"""验证代码计划契约和注册表的不变量。"""

from dataclasses import dataclass
from typing import cast

import pytest

from app.infrastructure.queue.errors import QueueConfigurationError
from app.infrastructure.queue.job import QueueJob
from app.interfaces.scheduler.contracts import CronSchedule, IntervalSchedule, QueueJobSchedule
from app.interfaces.scheduler.registry import ScheduleRegistry


@dataclass(frozen=True, slots=True)
class ExampleJob(QueueJob[object]):
    value: int

    async def handle(self, context: object) -> None:
        del context


def _definition(identifier: str, value: int = 1) -> QueueJobSchedule:
    return QueueJobSchedule(
        id=identifier,
        trigger=CronSchedule(hour=3),
        job=ExampleJob(value),
    )


def test_registry_returns_definitions_in_stable_id_order() -> None:
    registry = ScheduleRegistry()

    registry.add(_definition("reports.daily", 2))
    registry.add(_definition("cleanup.sessions", 1))

    assert tuple(definition.id for definition in registry.definitions) == (
        "cleanup.sessions",
        "reports.daily",
    )


def test_registry_rejects_duplicate_schedule_id() -> None:
    registry = ScheduleRegistry()
    registry.add(_definition("cleanup.sessions"))

    with pytest.raises(ValueError, match="重复"):
        registry.add(_definition("cleanup.sessions", 2))


@pytest.mark.parametrize("day_of_week", ["0", "0-4", "mon-5"])
def test_cron_schedule_rejects_numeric_weekdays(day_of_week: str) -> None:
    with pytest.raises(ValueError, match="不能使用数字"):
        CronSchedule(day_of_week=day_of_week)


@pytest.mark.parametrize("seconds", [True, 0, -1, 1.5])
def test_interval_schedule_requires_positive_integer_seconds(seconds: object) -> None:
    with pytest.raises(ValueError, match="正整数秒"):
        IntervalSchedule(cast(int, seconds))


def test_schedule_validates_job_payload_during_registration() -> None:
    with pytest.raises(QueueConfigurationError, match="必须继承 QueueJob"):
        QueueJobSchedule(
            id="invalid.job",
            trigger=CronSchedule(hour=3),
            job=object(),
        )
