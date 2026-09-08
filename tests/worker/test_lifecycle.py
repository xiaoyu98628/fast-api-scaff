"""验证 Worker 宿主、命令入口、资源生命周期和安全错误输出。"""

import asyncio
import subprocess
import sys
from dataclasses import replace
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
from app.interfaces.worker.resolver import JobResolver
from app.worker import app as worker_cli
from tests.console.test_application import build_settings
from tests.queue.fakes import FakeQueueBackend, Job, queue_backend_factory


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
async def test_worker_uses_production_resolver_and_drains_job(monkeypatch: pytest.MonkeyPatch) -> None:
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

    async def handle(job: Job) -> None:
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
    await container.queues.dispatch(Job(17))
    application = WorkerHost(
        settings,
        container_builder=lambda _: container,
        resolver_builder=lambda: JobResolver(("tests",)),
    )
    await asyncio.wait_for(application.serve(connection=None, queue=None, concurrency=2, stop=stop), 1)
    assert values == [17]
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
