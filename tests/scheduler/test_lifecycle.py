"""验证 Scheduler 宿主的启动、关闭、日志和错误边界。"""

import asyncio
import logging
from dataclasses import FrozenInstanceError, dataclass, replace
from unittest.mock import Mock

import pytest

import app.interfaces.scheduler.cli as scheduler_cli_module
from app.bootstrap.build import build_application_container
from app.bootstrap.scheduler.application import SchedulerHost
from app.infrastructure.queue.errors import QueueConfigurationError
from app.infrastructure.queue.job import QueueJob
from app.interfaces.scheduler.cli import run_scheduler
from app.interfaces.scheduler.contracts import CronSchedule, QueueJobSchedule
from app.interfaces.scheduler.registry import ScheduleRegistry
from tests.console.test_application import build_settings
from tests.scheduler.fakes import FakeSchedulerEngine


@dataclass(frozen=True, slots=True)
class ExampleJob(QueueJob[object]):
    async def handle(self, context: object) -> None:
        del context


def test_scheduler_host_keeps_an_immutable_settings_snapshot() -> None:
    settings = build_settings()
    application = SchedulerHost(settings)

    assert application.settings is settings
    with pytest.raises(FrozenInstanceError):
        setattr(application, "settings", build_settings())


@pytest.mark.asyncio
async def test_scheduler_runs_empty_catalog_and_closes_engine_before_container(
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = build_settings()
    events: list[str] = []
    engine = FakeSchedulerEngine(events)
    base_container = build_application_container(settings)

    async def record_container_close() -> None:
        events.append("container.close")

    container = replace(
        base_container,
        async_shutdown_callbacks=(*base_container.async_shutdown_callbacks, record_container_close),
    )
    stop = asyncio.Event()
    stop.set()
    application = SchedulerHost(
        settings,
        container_builder=lambda _: container,
        registry_builder=ScheduleRegistry,
        engine_builder=lambda: engine,
    )
    caplog.set_level(logging.INFO, logger="app.bootstrap.scheduler.lifecycle")

    await application.serve(stop)

    assert events == ["start", "wait", "close", "container.close"]
    records = [record for record in caplog.records if record.name == "app.bootstrap.scheduler.lifecycle"]
    assert [getattr(record, "event", None) for record in records] == [
        "scheduler.starting",
        "scheduler.schedules_discovered",
        "scheduler.started",
        "scheduler.stopping",
        "scheduler.stopped",
    ]
    assert getattr(records[1], "details") == {"schedule_count": 0}


@pytest.mark.asyncio
async def test_scheduler_logs_catalog_failure_and_still_closes_runtime(
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = build_settings()

    def fail_catalog() -> ScheduleRegistry:
        raise ValueError("invalid schedule catalog")

    application = SchedulerHost(settings, registry_builder=fail_catalog)
    caplog.set_level(logging.INFO, logger="app.bootstrap.scheduler.lifecycle")

    with pytest.raises(ValueError, match="invalid schedule catalog"):
        await application.serve(asyncio.Event())

    events = [getattr(record, "event", None) for record in caplog.records if record.name == "app.bootstrap.scheduler.lifecycle"]
    assert events == [
        "scheduler.starting",
        "scheduler.start_failed",
        "scheduler.stopping",
        "scheduler.stopped",
    ]


def test_scheduler_cli_logs_sanitized_unexpected_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    logger = Mock()
    monkeypatch.setattr(scheduler_cli_module, "_logger", logger)

    def fail() -> None:
        raise ValueError("sensitive scheduler detail")

    with pytest.raises(SystemExit) as caught:
        run_scheduler(fail)

    assert caught.value.code == 1
    details = logger.error.call_args.kwargs["extra"]["details"]
    assert details["error_type"] == "builtins.ValueError"
    assert details["stacktrace"]
    assert "sensitive scheduler detail" not in repr(logger.error.call_args)


@pytest.mark.asyncio
async def test_scheduler_rejects_named_route_when_queue_is_not_configured() -> None:
    settings = build_settings()
    registry = ScheduleRegistry()
    registry.add(
        QueueJobSchedule(
            id="invalid.route",
            trigger=CronSchedule(hour=3),
            job=ExampleJob(),
            connection="missing",
            queue="maintenance",
        )
    )
    application = SchedulerHost(settings, registry_builder=lambda: registry)

    with pytest.raises(QueueConfigurationError, match="队列连接未配置"):
        await application.serve(asyncio.Event())
