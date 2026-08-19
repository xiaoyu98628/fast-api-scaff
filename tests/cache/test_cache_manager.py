import asyncio

import pytest

from app.config.cache import CacheSettings
from app.platform.cache.backends.memcached_cache import MemcachedCache
from app.platform.cache.backends.redis_cache import RedisCache
from app.platform.cache.errors import CacheConfigurationError
from app.platform.cache.manager import CacheManager


@pytest.mark.asyncio
async def test_connection_is_validated_on_first_use() -> None:
    settings = CacheSettings(
        default="broken",
        connections={"broken": {"driver": "redis"}},
        _env_file=None,
    )
    manager = CacheManager(settings)

    with pytest.raises(CacheConfigurationError, match="broken"):
        await manager.get()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("connection", "expected_type"),
    [
        (
            {"driver": "redis", "host": "127.0.0.1"},
            RedisCache,
        ),
        (
            {
                "driver": "memcached",
                "host": "127.0.0.1",
                "username": "user",
                "password": "secret",
            },
            MemcachedCache,
        ),
    ],
)
async def test_network_clients_are_created_without_connecting(
    connection: dict[str, object],
    expected_type: type[RedisCache] | type[MemcachedCache],
) -> None:
    settings = CacheSettings(
        default="main",
        connections={"main": connection},
        _env_file=None,
    )
    manager = CacheManager(settings)

    client = await manager.get()

    assert isinstance(client, expected_type)
    await manager.aclose()


@pytest.mark.asyncio
async def test_missing_default_connection_is_reported_on_first_use() -> None:
    manager = CacheManager(CacheSettings(_env_file=None))

    with pytest.raises(CacheConfigurationError, match="默认缓存连接"):
        await manager.get()


@pytest.mark.asyncio
async def test_default_and_named_connections_are_independent() -> None:
    settings = CacheSettings(
        default="session",
        connections={
            "session": {"driver": "redis", "host": "127.0.0.1"},
            "page": {"driver": "redis", "host": "127.0.0.1"},
        },
        _env_file=None,
    )
    manager = CacheManager(settings)

    page = await manager.get("page")

    assert manager.is_initialized("page") is True
    assert manager.is_initialized("session") is False

    session = await manager.get()

    assert session is not page
    await manager.aclose()
    assert manager.is_initialized("page") is False
    assert manager.is_initialized("session") is False


@pytest.mark.asyncio
async def test_concurrent_get_creates_named_client_once() -> None:
    settings = CacheSettings(
        default="main",
        connections={"main": {"driver": "redis", "host": "127.0.0.1"}},
        _env_file=None,
    )
    manager = CacheManager(settings)

    first, second = await asyncio.gather(manager.get(), manager.get())

    assert first is second
    await manager.aclose()
