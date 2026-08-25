from unittest.mock import AsyncMock, Mock

import pytest
from memcachio import Client, MemcachedItem
from redis.asyncio import Redis

from app.infrastructure.cache.backends.memcached import MemcachedCacheBackend
from app.infrastructure.cache.backends.memory import MemoryCacheBackend
from app.infrastructure.cache.backends.redis import RedisCacheBackend
from app.infrastructure.cache.clients.managed import ManagedCacheClient
from app.infrastructure.cache.contracts.client import NO_EXPIRATION
from app.infrastructure.cache.errors import CacheKeyError, CacheOperationError
from app.infrastructure.cache.key import CacheKeyBuilder


@pytest.mark.asyncio
async def test_managed_client_applies_key_and_default_ttl() -> None:
    backend = AsyncMock()
    backend.set.return_value = True
    cache = ManagedCacheClient(
        backend=backend,
        key_builder=CacheKeyBuilder("app", "session"),
        default_ttl=300,
    )

    await cache.set("token", b"value")
    await cache.set("permanent", b"value", ttl=NO_EXPIRATION)

    backend.set.assert_any_await("app:session:token", b"value", 300)
    backend.set.assert_any_await("app:session:permanent", b"value", None)


@pytest.mark.asyncio
@pytest.mark.parametrize("ttl", [0, -1, True])
async def test_managed_client_rejects_invalid_ttl(ttl: int) -> None:
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
    backend = MemoryCacheBackend(clock=lambda: now)

    await backend.set("key", b"value", ttl=5)
    assert await backend.get("key") == b"value"

    now = 15.0
    assert await backend.get("key") is None
    assert await backend.exists("key") is False


@pytest.mark.asyncio
async def test_redis_backend_uses_raw_key_and_translates_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Redis(host="127.0.0.1", decode_responses=False)
    set_value = AsyncMock(return_value=True)
    get_value = AsyncMock(side_effect=OSError("unavailable"))
    monkeypatch.setattr(client, "set", set_value)
    monkeypatch.setattr(client, "get", get_value)
    backend = RedisCacheBackend(client)

    assert await backend.set("app:key", b"value", 60) is True
    set_value.assert_awaited_once_with("app:key", b"value", ex=60)

    with pytest.raises(CacheOperationError, match="Redis") as captured:
        await backend.get("app:key")

    assert isinstance(captured.value.__cause__, OSError)
    await backend.aclose()


@pytest.mark.asyncio
async def test_memcached_backend_uses_encoded_raw_key(monkeypatch: pytest.MonkeyPatch) -> None:
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
    backend = MemcachedCacheBackend(client)

    assert await backend.set("app:page:home", b"value", 60) is True
    assert await backend.get("app:page:home") == b"value"
    await backend.aclose()

    set_value.assert_awaited_once_with(cache_key, b"value", expiry=60)
    get_value.assert_awaited_once_with(cache_key)
    close.assert_called_once_with()


def test_memcached_converts_long_relative_ttl_to_timestamp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.infrastructure.cache.backends.memcached.time.time", lambda: 1_000_000.0)

    assert MemcachedCacheBackend._expiry(2_592_001) == 3_592_001
