import asyncio

import pytest

from app.config.database import DatabaseSettings
from app.infrastructure.database.errors import DatabaseConfigurationError
from app.infrastructure.database.manager import DatabaseManager


@pytest.mark.asyncio
async def test_connection_is_validated_on_first_use() -> None:
    settings = DatabaseSettings(
        default="broken",
        connections={"broken": {"driver": "mysql"}},
        _env_file=None,
    )
    manager = DatabaseManager(settings)

    with pytest.raises(DatabaseConfigurationError, match="broken"):
        await manager.get()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("driver", "expected_driver"),
    [
        ("mysql", "mysql+asyncmy"),
        ("postgresql", "postgresql+asyncpg"),
        ("pgsql", "postgresql+asyncpg"),
    ],
)
async def test_network_drivers_create_engine_without_connecting(
    driver: str,
    expected_driver: str,
) -> None:
    settings = DatabaseSettings(
        default="main",
        connections={
            "main": {
                "driver": driver,
                "host": "127.0.0.1",
                "database": "main",
                "username": "user",
                "password": "secret",
            }
        },
        _env_file=None,
    )
    manager = DatabaseManager(settings)

    engine = await manager.get_engine()

    assert engine.url.drivername == expected_driver
    await manager.aclose()


@pytest.mark.asyncio
async def test_missing_default_connection_is_reported_on_first_use() -> None:
    manager = DatabaseManager(DatabaseSettings(_env_file=None))

    with pytest.raises(DatabaseConfigurationError, match="默认数据库连接"):
        await manager.get()


@pytest.mark.asyncio
async def test_default_and_named_connections_are_independent() -> None:
    settings = DatabaseSettings(
        default="main",
        connections={
            "main": {"driver": "sqlite", "database": ":memory:"},
            "reporting": {"driver": "sqlite", "database": ":memory:"},
        },
        _env_file=None,
    )
    manager = DatabaseManager(settings)

    reporting = await manager.get("reporting")

    assert manager.is_initialized("reporting") is True
    assert manager.is_initialized("main") is False

    main = await manager.get()

    assert main is not reporting
    await manager.aclose()
    assert manager.is_initialized("reporting") is False
    assert manager.is_initialized("main") is False


@pytest.mark.asyncio
async def test_concurrent_get_creates_named_resource_once() -> None:
    settings = DatabaseSettings(
        default="main",
        connections={"main": {"driver": "sqlite", "database": ":memory:"}},
        _env_file=None,
    )
    manager = DatabaseManager(settings)

    first, second = await asyncio.gather(manager.get(), manager.get())

    assert first is second
    await manager.aclose()


@pytest.mark.parametrize("initialize_first", [False, True])
@pytest.mark.asyncio
async def test_manager_rejects_gets_as_soon_as_close_starts(monkeypatch: pytest.MonkeyPatch, initialize_first: bool) -> None:
    manager = DatabaseManager(
        DatabaseSettings(_env_file=None, connections={name: {"driver": "sqlite", "database": ":memory:"} for name in ("first", "second")})
    )
    if initialize_first:
        await manager.get("first")
    await manager.get("second")
    closing_started = asyncio.Event()
    release = asyncio.Event()
    second_resource = manager._resources["second"]
    original_close = second_resource._closer

    async def delayed_close(resource):
        closing_started.set()
        await release.wait()
        await original_close(resource)

    monkeypatch.setattr(second_resource, "_closer", delayed_close)
    closing = asyncio.create_task(manager.aclose())
    try:
        await closing_started.wait()
        with pytest.raises(RuntimeError, match="已经关闭"):
            await manager.get("first")
        with pytest.raises(RuntimeError, match="已经关闭"):
            await manager.get("second")
        assert manager.is_initialized("first") is initialize_first
    finally:
        release.set()
        await closing
    await manager.aclose()
    assert not manager.is_initialized("first")
    assert not manager.is_initialized("second")


@pytest.mark.asyncio
async def test_failed_close_keeps_manager_closed_and_cleans_other_resources(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = DatabaseManager(
        DatabaseSettings(_env_file=None, connections={name: {"driver": "sqlite", "database": ":memory:"} for name in ("first", "second")})
    )
    await manager.get("first")
    await manager.get("second")
    second_resource = manager._resources["second"]
    original_close = second_resource._closer
    original_error = RuntimeError("close failed")

    async def failing_close(_resource):
        raise original_error

    monkeypatch.setattr(second_resource, "_closer", failing_close)
    try:
        with pytest.raises(ExceptionGroup) as captured:
            await manager.aclose()
        assert captured.value.exceptions == (original_error,)
        assert not manager.is_initialized("first")
        for name in ("first", "second"):
            with pytest.raises(RuntimeError, match="已经关闭"):
                await manager.get(name)
    finally:
        monkeypatch.setattr(second_resource, "_closer", original_close)
        await manager.aclose()
