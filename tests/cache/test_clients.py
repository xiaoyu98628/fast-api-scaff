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
async def test_redis_string_ttl_operations(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Redis(host="127.0.0.1", decode_responses=False)
    expire = AsyncMock(return_value=True)
    ttl = AsyncMock(return_value=120)
    monkeypatch.setattr(client, "expire", expire)
    monkeypatch.setattr(client, "ttl", ttl)
    storage = RedisStringStorage(client)

    assert await storage.expire("app:login:key", 900) is True
    assert await storage.ttl("app:login:key") == 120

    expire.assert_awaited_once_with("app:login:key", 900)
    ttl.assert_awaited_once_with("app:login:key")
    await client.aclose()


@pytest.mark.asyncio
async def test_managed_redis_client_applies_key_to_ttl_operations() -> None:
    storage = Mock(spec=RedisStorage)
    storage.strings = AsyncMock()
    storage.strings.expire.return_value = True
    storage.strings.ttl.return_value = 60
    cache = ManagedRedisCacheClient(
        storage=storage,
        key_builder=CacheKeyBuilder("app", "security"),
        default_ttl=300,
    )

    assert await cache.expire("login", ttl=900) is True
    assert await cache.ttl("login") == 60

    storage.strings.expire.assert_awaited_once_with("app:security:login", 900)
    storage.strings.ttl.assert_awaited_once_with("app:security:login")


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


@pytest.mark.asyncio
async def test_script_execution_prefixes_every_key_and_preserves_raw_result() -> None:
    client = Mock(spec=Redis)
    result = [b"value", 12, None]
    client.eval = AsyncMock(return_value=result)
    cache = ManagedRedisCacheClient(RedisStorage(client), CacheKeyBuilder("app", "shared"), default_ttl=300)
    script = "return {redis.call('GET', KEYS[1]), ARGV[1]}"
    assert await cache.execute_script(script, keys=("first", "second"), args=(12, b"bytes", "text")) is result
    client.eval.assert_awaited_once_with(script, 2, "app:shared:first", "app:shared:second", 12, b"bytes", "text")
    client.expire.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "script,keys,args",
    [
        ("", ("key",), ()),
        ("return 1", (), ()),
        ("return 1", ["key"], ()),
        ("return 1", ("key",), (True,)),
        ("return 1", ("key",), (1.2,)),
        ("return 1", ("key",), [1]),
    ],
)
async def test_script_execution_rejects_invalid_transport_arguments(script, keys, args) -> None:
    client = Mock(spec=Redis)
    client.eval = AsyncMock()
    cache = ManagedRedisCacheClient(RedisStorage(client), CacheKeyBuilder("app"), default_ttl=None)
    with pytest.raises(ValueError):
        await cache.execute_script(script, keys=keys, args=args)
    client.eval.assert_not_awaited()


@pytest.mark.asyncio
async def test_script_execution_validates_all_keys_before_io() -> None:
    client = Mock(spec=Redis)
    client.eval = AsyncMock()
    cache = ManagedRedisCacheClient(RedisStorage(client), CacheKeyBuilder("app"), default_ttl=None)
    with pytest.raises(CacheKeyError):
        await cache.execute_script("return 1", keys=("valid", "bad key"))
    client.eval.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_script_execution_translates_driver_errors_but_preserves_cancellation(cancel: bool) -> None:
    import asyncio

    from redis.exceptions import ResponseError

    error = asyncio.CancelledError() if cancel else ResponseError("invalid state")
    client = Mock(spec=Redis)
    client.eval = AsyncMock(side_effect=error)
    cache = ManagedRedisCacheClient(RedisStorage(client), CacheKeyBuilder("app"), default_ttl=None)
    with pytest.raises(asyncio.CancelledError if cancel else CacheOperationError) as captured:
        await cache.execute_script("return 1", keys=("key",))
    if cancel:
        assert captured.value is error
    else:
        assert captured.value.__cause__ is error
