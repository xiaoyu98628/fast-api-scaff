import asyncio

import pytest
from typer.testing import CliRunner

from app.bootstrap.app import create_app
from app.bootstrap.build import build_application_container
from app.config.queue import QueueSettings
from app.infrastructure.queue.errors import QueueError
from app.interfaces.console.commands.queue import list_failures
from app.interfaces.console.context import ConsoleContext
from app.interfaces.worker.application import WorkerApplication
from app.interfaces.worker.main import app as worker_cli
from app.interfaces.worker.registry import HandlerRegistry
from tests.console.test_application import build_settings
from tests.queue.test_core import Job, definition


@pytest.mark.asyncio
async def test_http_lifespan_does_not_initialize_queue() -> None:
    settings = build_settings().model_copy(
        update={"queue": QueueSettings(_env_file=None, default="main", connections={"main": {"driver": "memory"}})}
    )
    container = build_application_container(settings)
    app = create_app(settings, container_builder=lambda _: container)
    async with app.router.lifespan_context(app):
        assert not container.queues.is_initialized()


@pytest.mark.asyncio
async def test_worker_uses_own_runtime_and_drains_job() -> None:
    settings = build_settings().model_copy(
        update={"queue": QueueSettings(_env_file=None, default="main", connections={"main": {"driver": "memory"}})}
    )
    container = build_application_container(settings)
    container.queues.catalog.register(definition())
    stop = asyncio.Event()
    values: list[int] = []

    async def handle(job: Job) -> None:
        values.append(job.value)
        stop.set()

    registry = HandlerRegistry()
    registry.register(definition(), handle)
    await (await container.queues.get()).dispatch(Job(17))
    application = WorkerApplication(container_builder=lambda _: container, registry_builder=lambda _: registry)
    await asyncio.wait_for(application.serve(settings, connection="main", queue=None, concurrency=2, stop=stop), 1)
    assert values == [17]
    with pytest.raises(QueueError):
        await container.queues.get()


@pytest.mark.asyncio
async def test_console_rejects_memory_failures_instead_of_empty_list() -> None:
    settings = build_settings()
    container = build_application_container(settings)
    with pytest.raises(QueueError, match="独立 Console"):
        await list_failures(ConsoleContext(settings, container), limit=20, offset=0)
    await container.aclose()


def test_worker_help_has_independent_connection_queue_and_concurrency() -> None:
    result = CliRunner().invoke(worker_cli, ["--help"])
    assert result.exit_code == 0
    assert "connection" in result.output
    assert "queue" in result.output
    assert "concurrency" in result.output
