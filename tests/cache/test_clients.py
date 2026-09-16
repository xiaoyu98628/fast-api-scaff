"""验证统一缓存客户端的 key、TTL 和写入语义。"""

from unittest.mock import AsyncMock, Mock

import pytest
from memcachio import Client, MemcachedItem
from redis.asyncio import Redis

from app.infrastructure.cache.clients.managed import ManagedCacheClient
from app.infrastructure.cache.clients.redis import ManagedRedisCacheClient
from app.infrastructure.cache.connections.memcached import MemcachedCacheConnection
from app.infrastructure.cache.connections.redis import RedisCacheConnection
from app.infrastructure.cache.contracts.client import NO_EXPIRATION, CacheTTL
from app.infrastructure.cache.errors import CacheKeyError, CacheOperationError
from app.infrastructure.cache.key import CacheKeyBuilder
from app.infrastructure.cache.storages.memcached import MemcachedCacheStorage
from app.infrastructure.cache.storages.redis.base import BaseRedisStorage
from app.infrastructure.cache.storages.redis.storage import RedisStorage
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
async def test_redis_storage_uses_raw_key_and_translates_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Redis(host="127.0.0.1", decode_responses=False)
    set_value = AsyncMock(return_value=True)
    get_value = AsyncMock(side_effect=OSError("unavailable"))
    monkeypatch.setattr(client, "set", set_value)
    monkeypatch.setattr(client, "get", get_value)
    connection = RedisCacheConnection(client)
    storage = RedisStorage(client)

    assert isinstance(storage.strings, RedisStringStorage)
    assert isinstance(storage.strings, BaseRedisStorage)
    assert await storage.set("app:key", b"value", 60) is True
    set_value.assert_awaited_once_with("app:key", b"value", ex=60)

    with pytest.raises(CacheOperationError, match="Redis") as captured:
        await storage.get("app:key")

    assert isinstance(captured.value.__cause__, OSError)
    await connection.aclose()


@pytest.mark.asyncio
async def test_redis_string_atomic_counter_and_ttl_operations(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Redis(host="127.0.0.1", decode_responses=False)
    evaluate = AsyncMock(return_value=3)
    expire = AsyncMock(return_value=True)
    ttl = AsyncMock(return_value=120)
    monkeypatch.setattr(client, "eval", evaluate)
    monkeypatch.setattr(client, "expire", expire)
    monkeypatch.setattr(client, "ttl", ttl)
    storage = RedisStringStorage(client)

    assert await storage.increment("app:login:key", 300) == 3
    assert await storage.expire("app:login:key", 900) is True
    assert await storage.ttl("app:login:key") == 120

    assert evaluate.await_args is not None
    script, key_count, key, initial_ttl = evaluate.await_args.args
    assert "INCR" in script
    assert (key_count, key, initial_ttl) == (1, "app:login:key", 300)
    expire.assert_awaited_once_with("app:login:key", 900)
    ttl.assert_awaited_once_with("app:login:key")
    await client.aclose()


@pytest.mark.asyncio
async def test_managed_redis_client_applies_key_to_atomic_operations() -> None:
    storage = Mock(spec=RedisStorage)
    storage.strings = AsyncMock()
    storage.strings.increment.return_value = 2
    storage.strings.expire.return_value = True
    storage.strings.ttl.return_value = 60
    cache = ManagedRedisCacheClient(
        storage=storage,
        key_builder=CacheKeyBuilder("app", "security"),
        default_ttl=300,
    )

    assert await cache.increment("login", ttl=120) == 2
    assert await cache.expire("login", ttl=900) is True
    assert await cache.ttl("login") == 60

    storage.strings.increment.assert_awaited_once_with("app:security:login", 120)
    storage.strings.expire.assert_awaited_once_with("app:security:login", 900)
    storage.strings.ttl.assert_awaited_once_with("app:security:login")


@pytest.mark.asyncio
async def test_managed_window_uses_namespaced_key_and_explicit_duration() -> None:
    storage = Mock(spec=RedisStorage)
    storage.strings = AsyncMock()
    storage.strings.acquire_window.return_value = (False, 500)
    cache = ManagedRedisCacheClient(storage, CacheKeyBuilder("app", "security"), default_ttl=300)
    assert await cache.acquire_window("quota", limit=1000, window_ms=60_000) == (False, 500)
    storage.strings.acquire_window.assert_awaited_once_with("app:security:quota", 1000, 60_000)


@pytest.mark.asyncio
@pytest.mark.parametrize("limit,window", [(0, 1000), (True, 1000), (1_000_001, 1000), (1, 0), (1, 86_400_001)])
async def test_managed_window_rejects_invalid_parameters(limit: int, window: int) -> None:
    storage = Mock(spec=RedisStorage)
    storage.strings = AsyncMock()
    cache = ManagedRedisCacheClient(storage, CacheKeyBuilder("app"), default_ttl=None)
    with pytest.raises(ValueError):
        await cache.acquire_window("quota", limit=limit, window_ms=window)
    storage.strings.acquire_window.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("result,expected", [([1, 0], (True, 0)), ([0, 0], (False, 0)), ([0, 60_000], (False, 60_000))])
async def test_window_is_one_atomic_operation(result: list[int], expected: tuple[bool, int]) -> None:
    client = Mock(spec=Redis)
    client.eval = AsyncMock(return_value=result)
    assert await RedisStringStorage(client).acquire_window("app:quota", 1000, 60_000) == expected
    client.eval.assert_awaited_once()
    assert client.eval.await_args is not None
    assert client.eval.await_args.args[1:] == (1, "app:quota", 1000, 60_000)


@pytest.mark.asyncio
@pytest.mark.parametrize("result", [None, [], [1], [1, 1], [0, -1], [0, 60_001], [True, 0], [0, False], [2, 0], ["1", 0]])
async def test_window_rejects_invalid_script_results(result: object) -> None:
    client = Mock(spec=Redis)
    client.eval = AsyncMock(return_value=result)
    with pytest.raises(CacheOperationError):
        await RedisStringStorage(client).acquire_window("app:quota", 1000, 60_000)


@pytest.mark.asyncio
async def test_window_translates_driver_failure() -> None:
    client = Mock(spec=Redis)
    client.eval = AsyncMock(side_effect=OSError("unavailable"))
    with pytest.raises(CacheOperationError) as captured:
        await RedisStringStorage(client).acquire_window("app:quota", 1000, 60_000)
    assert isinstance(captured.value.__cause__, OSError)


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
