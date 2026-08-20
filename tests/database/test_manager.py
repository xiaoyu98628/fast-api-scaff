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
