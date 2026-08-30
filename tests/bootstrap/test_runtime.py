import pytest

from app.bootstrap.container import ApplicationContainer
from app.bootstrap.runtime import ApplicationRuntime
from app.config.cache import CacheSettings
from app.config.database import DatabaseSettings
from app.contexts.user.composition import build_user_context
from app.infrastructure.cache.manager import CacheManager
from app.infrastructure.database.manager import DatabaseManager


def build_container(
    *,
    startup_callbacks=(),
    async_shutdown_callbacks=(),
) -> ApplicationContainer:
    databases = DatabaseManager(DatabaseSettings(_env_file=None))
    caches = CacheManager(CacheSettings(_env_file=None))
    return ApplicationContainer(
        databases=databases,
        caches=caches,
        users=build_user_context(databases),
        startup_callbacks=startup_callbacks,
        async_shutdown_callbacks=(*async_shutdown_callbacks, databases.aclose, caches.aclose),
    )


@pytest.mark.asyncio
async def test_runtime_starts_and_closes_container() -> None:
    events: list[str] = []

    async def start() -> None:
        events.append("start")

    async def stop() -> None:
        events.append("stop")

    container = build_container(startup_callbacks=(start,), async_shutdown_callbacks=(stop,))
    runtime = ApplicationRuntime(lambda: container)

    async with runtime as active_container:
        assert active_container is container
        assert runtime.container is container
        assert events == ["start"]

    assert runtime.container is None
    assert events == ["start", "stop"]


@pytest.mark.asyncio
async def test_runtime_closes_container_when_start_fails() -> None:
    events: list[str] = []

    async def fail_start() -> None:
        events.append("start")
        raise RuntimeError("startup failed")

    async def stop() -> None:
        events.append("stop")

    container = build_container(startup_callbacks=(fail_start,), async_shutdown_callbacks=(stop,))
    runtime = ApplicationRuntime(lambda: container)

    with pytest.raises(RuntimeError, match="startup failed"):
        await runtime.start()

    assert runtime.container is None
    assert events == ["start", "stop"]


@pytest.mark.asyncio
async def test_runtime_rejects_repeated_start() -> None:
    runtime = ApplicationRuntime(build_container)
    await runtime.start()

    try:
        with pytest.raises(RuntimeError, match="已经启动"):
            await runtime.start()
    finally:
        await runtime.aclose()
