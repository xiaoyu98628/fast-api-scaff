"""验证 Worker 宿主、命令入口、资源生命周期和安全错误输出。"""

import asyncio
import logging
import subprocess
import sys
from dataclasses import FrozenInstanceError, replace
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

import app.interfaces.worker.cli as worker_cli_module
from app.bootstrap.build import build_application_container
from app.bootstrap.worker.application import WorkerHost
from app.config.database import DatabaseSettings
from app.config.queue import QueueSettings
from app.infrastructure.queue.errors import QueueError
from app.infrastructure.queue.failed.sql.model import FailedJobModel
from app.infrastructure.queue.manager import QueueManager
from app.interfaces.worker.cli import run_worker
from app.interfaces.worker.context import JobExecutionContext
from app.interfaces.worker.resolver import JobResolver
from app.worker import app as worker_cli
from tests.console.test_application import build_settings
from tests.queue.fakes import FakeQueueBackend, Job, queue_backend_factory


def test_worker_host_keeps_an_immutable_settings_snapshot() -> None:
    settings = build_settings()
    application = WorkerHost(settings)

    assert application.settings is settings
    with pytest.raises(FrozenInstanceError):
        setattr(application, "settings", build_settings())


def test_worker_cli_logs_sanitized_unexpected_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """未知故障保留类型和栈位置，但不记录异常消息。"""

    logger = Mock()
    monkeypatch.setattr(worker_cli_module, "_logger", logger)

    def fail() -> None:
        raise ValueError("sensitive worker detail")

    with pytest.raises(SystemExit) as caught:
        run_worker(fail)

    assert caught.value.code == 1
    details = logger.error.call_args.kwargs["extra"]["details"]
    assert details["error_type"] == "builtins.ValueError"
    assert details["stacktrace"]
    assert "sensitive worker detail" not in repr(logger.error.call_args)


@pytest.mark.asyncio
async def test_worker_logs_startup_failure_and_completed_cleanup(caplog: pytest.LogCaptureFixture) -> None:
    settings = build_settings()

    async def fail_startup() -> None:
        raise RuntimeError("startup failed")

    container = replace(
        build_application_container(settings),
        startup_callbacks=(fail_startup,),
    )
    application = WorkerHost(settings, container_builder=lambda _: container)

    caplog.set_level(logging.INFO, logger="app.bootstrap.worker.lifecycle")
    with pytest.raises(RuntimeError, match="startup failed"):
        await application.serve(connection=None, queue=None, concurrency=None, stop=asyncio.Event())

    events = [getattr(record, "event", None) for record in caplog.records if record.name == "app.bootstrap.worker.lifecycle"]
    assert events == [
        "worker.starting",
        "worker.start_failed",
        "worker.stopping",
        "worker.stopped",
    ]


@pytest.mark.asyncio
async def test_worker_logs_shutdown_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = build_settings()

    async def fail_shutdown() -> None:
        raise RuntimeError("shutdown failed")

    async def consume_nothing(*_args, **_kwargs) -> None:
        pass

    container = replace(
        build_application_container(settings),
        async_shutdown_callbacks=(fail_shutdown,),
    )
    application = WorkerHost(settings, container_builder=lambda _: container)
    monkeypatch.setattr(WorkerHost, "_consume", consume_nothing)

    caplog.set_level(logging.INFO, logger="app.bootstrap.worker.lifecycle")
    with pytest.raises(ExceptionGroup, match="shutdown callbacks failed"):
        await application.serve(connection=None, queue=None, concurrency=None, stop=asyncio.Event())

    events = [getattr(record, "event", None) for record in caplog.records if record.name == "app.bootstrap.worker.lifecycle"]
    assert events == [
        "worker.starting",
        "worker.started",
        "worker.stopping",
        "worker.stop_failed",
    ]


@pytest.mark.asyncio
async def test_worker_uses_production_resolver_and_drains_job(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = build_settings().model_copy(
        update={
            "database": DatabaseSettings(
                _env_file=None,
                default="main",
                connections={"main": {"driver": "sqlite", "database": ":memory:"}},
            ),
            "queue": QueueSettings(
                _env_file=None,
                default="main",
                connections={"main": {"driver": "redis", "host": "localhost"}},
            ),
        }
    )
    base_container = build_application_container(settings)
    stop = asyncio.Event()
    values: list[int] = []

    job_id = None

    async def handle(job: Job, context: JobExecutionContext) -> None:
        assert context.settings is settings
        assert context.container is container
        assert context.job.id == job_id
        assert context.job.reference.endswith(":Job")
        assert context.job.queue_connection == "main"
        assert context.job.queue_name == "default"
        assert context.job.correlation_id == "request-123"
        values.append(job.value)
        stop.set()

    monkeypatch.setattr(Job, "handle", handle)

    queues = QueueManager(
        settings.queue,
        base_container.databases,
        factory=queue_backend_factory(FakeQueueBackend()),
    )
    container = replace(
        base_container,
        queues=queues,
        async_shutdown_callbacks=(*base_container.async_shutdown_callbacks[:-1], queues.aclose),
    )
    engine = await container.databases.get_engine("main")
    async with engine.begin() as connection:
        await connection.run_sync(FailedJobModel.metadata.create_all)
    job_id = await container.queues.dispatch(Job(17), correlation_id="request-123")
    application = WorkerHost(
        settings,
        container_builder=lambda _: container,
        resolver_builder=lambda: JobResolver(("tests",)),
    )
    caplog.set_level(logging.INFO, logger="app.bootstrap.worker.lifecycle")
    await asyncio.wait_for(application.serve(connection=None, queue=None, concurrency=2, stop=stop), 1)
    assert values == [17]
    events = [getattr(record, "event", None) for record in caplog.records if record.name == "app.bootstrap.worker.lifecycle"]
    assert events == [
        "worker.starting",
        "worker.started",
        "worker.stopping",
        "worker.stopped",
    ]
    with pytest.raises(QueueError):
        await container.queues.get()


def test_worker_help_has_independent_connection_queue_and_concurrency() -> None:
    result = CliRunner().invoke(worker_cli, ["--help"])
    assert result.exit_code == 0
    assert "connection" in result.output
    assert "queue" in result.output
    assert "concurrency" in result.output
    assert "消费并执行队列中的后台任务" in result.output
    assert "已注册" not in result.output


def test_worker_module_is_executable() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "app.worker", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert "connection" in result.stdout
