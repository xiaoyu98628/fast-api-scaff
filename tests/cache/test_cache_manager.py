import asyncio

import pytest

from app.config.cache import CacheSettings
from app.infrastructure.cache.clients.managed import ManagedCacheClient
from app.infrastructure.cache.errors import CacheConfigurationError
from app.infrastructure.cache.manager import CacheManager


def test_invalid_connection_is_reported_when_manager_is_built() -> None:
    settings = CacheSettings(
        default="broken",
        namespace="test",
        connections={"broken": {"driver": "redis"}},
        _env_file=None,
    )

    with pytest.raises(CacheConfigurationError, match="broken"):
        CacheManager(settings)


def test_configured_connection_requires_namespace() -> None:
    settings = CacheSettings(
        default="main",
        connections={"main": {"driver": "memory"}},
        _env_file=None,
    )

    with pytest.raises(CacheConfigurationError, match="CACHE_NAMESPACE"):
        CacheManager(settings)


def test_default_connection_must_exist() -> None:
    settings = CacheSettings(default="missing", namespace="test", _env_file=None)

    with pytest.raises(CacheConfigurationError, match="missing"):
        CacheManager(settings)


@pytest.mark.asyncio
async def test_network_client_is_created_without_connecting() -> None:
    settings = CacheSettings(
        default="main",
        namespace="test",
        connections={"main": {"driver": "redis", "host": "127.0.0.1"}},
        _env_file=None,
    )
    manager = CacheManager(settings)

    client = await manager.get()

    assert isinstance(client, ManagedCacheClient)
    assert manager.is_initialized() is True
    await manager.aclose()


@pytest.mark.asyncio
async def test_default_and_named_connections_are_independent() -> None:
    settings = CacheSettings(
        default="session",
        namespace="test",
        connections={
            "session": {"driver": "memory", "key_prefix": "session"},
            "page": {"driver": "memory", "key_prefix": "page"},
        },
        _env_file=None,
    )
    manager = CacheManager(settings)

    page = await manager.get("page")
    await page.set("home", b"page")

    assert manager.is_initialized("page") is True
    assert manager.is_initialized("session") is False

    session = await manager.get()
    assert session is not page
    assert await session.get("home") is None

    await manager.aclose()
    assert manager.is_initialized("page") is False
    assert manager.is_initialized("session") is False


@pytest.mark.asyncio
async def test_concurrent_get_creates_named_client_once() -> None:
    settings = CacheSettings(
        default="main",
        namespace="test",
        connections={"main": {"driver": "memory"}},
        _env_file=None,
    )
    manager = CacheManager(settings)

    first, second = await asyncio.gather(manager.get(), manager.get())

    assert first is second
    assert await manager.ping() is True
    await manager.aclose()


@pytest.mark.asyncio
async def test_missing_default_is_reported_when_implicit_connection_is_requested() -> None:
    manager = CacheManager(CacheSettings(_env_file=None))

    with pytest.raises(CacheConfigurationError, match="默认缓存连接"):
        await manager.get()
