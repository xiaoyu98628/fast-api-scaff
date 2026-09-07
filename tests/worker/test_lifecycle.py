import asyncio
import subprocess
import sys
from dataclasses import replace

import pytest
from typer.testing import CliRunner

from app.bootstrap.build import build_application_container
from app.bootstrap.http.application import create_app
from app.bootstrap.worker.application import WorkerHost
from app.config.database import DatabaseSettings
from app.config.queue import QueueSettings
from app.infrastructure.queue.errors import QueueError
from app.infrastructure.queue.failed.sql.model import FailedJobModel
from app.infrastructure.queue.manager import QueueManager
from app.interfaces.console.commands.queue import list_failures
from app.interfaces.console.context import ConsoleContext
from app.interfaces.worker.registry import HandlerRegistry
from app.worker import app as worker_cli
from tests.console.test_application import build_settings
from tests.queue.fakes import FakeQueueBackend, queue_backend_factory
from tests.queue.test_core import Job, definition


@pytest.mark.asyncio
async def test_http_lifespan_does_not_initialize_queue() -> None:
    settings = build_settings().model_copy(
        update={
            "queue": QueueSettings(
                _env_file=None,
                default="main",
                connections={"main": {"driver": "redis", "host": "localhost"}},
            )
        }
    )
    container = build_application_container(settings)
    app = create_app(settings, container_builder=lambda _: container)
    async with app.router.lifespan_context(app):
        assert not container.queues.is_initialized()


@pytest.mark.asyncio
async def test_worker_uses_own_runtime_and_drains_job() -> None:
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
    container.queues.catalog.register(definition())
    stop = asyncio.Event()
    values: list[int] = []

    async def handle(job: Job) -> None:
        values.append(job.value)
        stop.set()

    registry = HandlerRegistry()
    registry.register(definition(), handle)
    await (await container.queues.get()).dispatch(Job(17))
    application = WorkerHost(settings, container_builder=lambda _: container, registry_builder=lambda _: registry)
    await asyncio.wait_for(application.serve(connection="main", queue=None, concurrency=2, stop=stop), 1)
    assert values == [17]
    with pytest.raises(QueueError):
        await container.queues.get()


@pytest.mark.asyncio
async def test_console_rejects_unconfigured_failure_database() -> None:
    settings = build_settings()
    container = build_application_container(settings)
    with pytest.raises(QueueError, match="SQL 失败存储数据库未配置"):
        await list_failures(ConsoleContext(settings, container), limit=20, offset=0)
    await container.aclose()


def test_worker_help_has_independent_connection_queue_and_concurrency() -> None:
    result = CliRunner().invoke(worker_cli, ["--help"])
    assert result.exit_code == 0
    assert "connection" in result.output
    assert "queue" in result.output
    assert "concurrency" in result.output


def test_worker_module_is_executable() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "app.worker", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert "connection" in result.stdout
