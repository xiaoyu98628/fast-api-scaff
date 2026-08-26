from unittest.mock import AsyncMock, Mock

import pytest
from memcachio import Client, MemcachedItem
from redis.asyncio import Redis

from app.infrastructure.cache.clients.managed import ManagedCacheClient
from app.infrastructure.cache.connections.memcached import MemcachedCacheConnection
from app.infrastructure.cache.connections.memory import MemoryCacheConnection
from app.infrastructure.cache.connections.redis import RedisCacheConnection
from app.infrastructure.cache.contracts.client import NO_EXPIRATION, CacheTTL
from app.infrastructure.cache.errors import CacheKeyError, CacheOperationError
from app.infrastructure.cache.key import CacheKeyBuilder
from app.infrastructure.cache.storages.memcached import MemcachedCacheStorage
from app.infrastructure.cache.storages.memory import MemoryCacheStorage
from app.infrastructure.cache.storages.redis.string import RedisStringStorage


@pytest.mark.asyncio
async def test_managed_client_applies_key_and_default_ttl() -> None:
    storage = AsyncMock()
    storage.set.return_value = True
    cache = ManagedCacheClient(
        storage=storage,
        key_builder=CacheKeyBuilder("app", "session"),
        default_ttl=300,
    )

    await cache.set("token", b"value")
    await cache.set("permanent", b"value", ttl=NO_EXPIRATION)

    storage.set.assert_any_await("app:session:token", b"value", 300)
    storage.set.assert_any_await("app:session:permanent", b"value", None)


@pytest.mark.asyncio
@pytest.mark.parametrize("ttl", [0, -1, True, 1.5])
async def test_managed_client_rejects_invalid_ttl(ttl: CacheTTL) -> None:
    cache = ManagedCacheClient(AsyncMock(), CacheKeyBuilder("app"), default_ttl=None)

    with pytest.raises(ValueError, match="ttl"):
        await cache.set("key", b"value", ttl=ttl)


@pytest.mark.parametrize("key", ["", "has space", "line\nbreak", "a" * 251])
def test_key_builder_rejects_non_portable_keys(key: str) -> None:
    with pytest.raises(CacheKeyError):
        CacheKeyBuilder("app").build(key)


@pytest.mark.asyncio
async def test_memory_cache_expires_values_using_monotonic_clock() -> None:
    now = 10.0
    connection = MemoryCacheConnection(clock=lambda: now)
    storage = MemoryCacheStorage(connection)

    await storage.set("key", b"value", ttl=5)
    assert await storage.get("key") == b"value"

    now = 15.0
    assert await storage.get("key") is None
    assert await storage.exists("key") is False


@pytest.mark.asyncio
async def test_redis_storage_uses_raw_key_and_translates_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Redis(host="127.0.0.1", decode_responses=False)
    set_value = AsyncMock(return_value=True)
    get_value = AsyncMock(side_effect=OSError("unavailable"))
    monkeypatch.setattr(client, "set", set_value)
    monkeypatch.setattr(client, "get", get_value)
    connection = RedisCacheConnection(client)
    storage = RedisStringStorage(client)

    assert await storage.set("app:key", b"value", 60) is True
    set_value.assert_awaited_once_with("app:key", b"value", ex=60)

    with pytest.raises(CacheOperationError, match="Redis") as captured:
        await storage.get("app:key")

    assert isinstance(captured.value.__cause__, OSError)
    await connection.aclose()


@pytest.mark.asyncio
async def test_memcached_storage_uses_encoded_raw_key(monkeypatch: pytest.MonkeyPatch) -> None:
    client: Client[bytes] = Client(("127.0.0.1", 11211), decode_responses=False)
    cache_key = b"app:page:home"
    set_value = AsyncMock(return_value=True)
    get_value = AsyncMock(
        return_value={
            cache_key: MemcachedItem(
                key=cache_key,
                flags=0,
                size=5,
                cas=None,
                value=b"value",
            )
        }
    )
    close = Mock()
    monkeypatch.setattr(client, "set", set_value)
    monkeypatch.setattr(client, "get", get_value)
    monkeypatch.setattr(client.connection_pool, "close", close)
    connection = MemcachedCacheConnection(client)
    storage = MemcachedCacheStorage(client)

    assert await storage.set("app:page:home", b"value", 60) is True
    assert await storage.get("app:page:home") == b"value"
    await connection.aclose()

    set_value.assert_awaited_once_with(cache_key, b"value", expiry=60)
    get_value.assert_awaited_once_with(cache_key)
    close.assert_called_once_with()


def test_memcached_converts_long_relative_ttl_to_timestamp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.infrastructure.cache.storages.memcached.time.time", lambda: 1_000_000.0)

    assert MemcachedCacheStorage._expiry(2_592_001) == 3_592_001
