"""验证缓存客户端的数据类型、key、TTL、取消与脚本传输语义。"""

import logging
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
from app.infrastructure.cache.storages.redis.hash import RedisHashStorage
from app.infrastructure.cache.storages.redis.key import RedisKeyStorage
from app.infrastructure.cache.storages.redis.set import RedisSetStorage
from app.infrastructure.cache.storages.redis.sorted_set import RedisSortedSetStorage
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
    assert isinstance(storage.keys, RedisKeyStorage)
    assert isinstance(storage.keys, BaseRedisStorage)
    assert isinstance(storage.sorted_sets, RedisSortedSetStorage)
    assert isinstance(storage.sorted_sets, BaseRedisStorage)
    assert isinstance(storage.hashes, RedisHashStorage)
    assert isinstance(storage.sets, RedisSetStorage)
    assert isinstance(storage.hashes, BaseRedisStorage)
    assert isinstance(storage.sets, BaseRedisStorage)
    assert await storage.set("app:key", b"value", 60) is True
    set_value.assert_awaited_once_with("app:key", b"value", ex=60)

    with pytest.raises(CacheOperationError, match="Redis") as captured:
        await storage.get("app:key")

    assert isinstance(captured.value.__cause__, OSError)
    await connection.aclose()


@pytest.mark.asyncio
async def test_redis_key_operations(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Redis(host="127.0.0.1", decode_responses=False)
    delete = AsyncMock(return_value=1)
    exists = AsyncMock(return_value=1)
    expire = AsyncMock(return_value=True)
    ttl = AsyncMock(return_value=120)
    monkeypatch.setattr(client, "delete", delete)
    monkeypatch.setattr(client, "exists", exists)
    monkeypatch.setattr(client, "expire", expire)
    monkeypatch.setattr(client, "ttl", ttl)
    storage = RedisKeyStorage(client)

    assert await storage.delete("app:login:key") is True
    assert await storage.exists("app:login:key") is True
    assert await storage.expire("app:login:key", 900) is True
    assert await storage.ttl("app:login:key") == 120

    delete.assert_awaited_once_with("app:login:key")
    exists.assert_awaited_once_with("app:login:key")
    expire.assert_awaited_once_with("app:login:key", 900)
    ttl.assert_awaited_once_with("app:login:key")
    await client.aclose()


@pytest.mark.asyncio
async def test_managed_redis_client_applies_key_to_ttl_operations() -> None:
    storage = Mock(spec=RedisStorage)
    storage.keys = AsyncMock()
    storage.keys.expire.return_value = True
    storage.keys.ttl.return_value = 60
    cache = ManagedRedisCacheClient(
        storage=storage,
        key_builder=CacheKeyBuilder("app", "security"),
        default_ttl=300,
    )

    assert await cache.expire("login", ttl=900) is True
    assert await cache.ttl("login") == 60

    storage.keys.expire.assert_awaited_once_with("app:security:login", 900)
    storage.keys.ttl.assert_awaited_once_with("app:security:login")


@pytest.mark.asyncio
@pytest.mark.parametrize("minimum,maximum,offset", [(float("-inf"), 100, 0), (1.5, float("inf"), 2)])
async def test_sorted_set_query_preserves_range_limit_prefix_and_driver_order(minimum: int | float, maximum: int | float, offset: int) -> None:
    client = Mock(spec=Redis)
    client.zrangebyscore = AsyncMock(return_value=[b"u2", b"u1"])
    cache = ManagedRedisCacheClient(RedisStorage(client), CacheKeyBuilder("app", "shared"), default_ttl=300)

    assert await cache.sorted_set_range_by_score("queue", minimum=minimum, maximum=maximum, count=2, offset=offset) == (b"u2", b"u1")
    client.zrangebyscore.assert_awaited_once_with("app:shared:queue", minimum, maximum, start=offset, num=2)
    client.eval.assert_not_called()
    client.zrem.assert_not_called()
    client.expire.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "minimum,maximum,offset,count",
    [
        (float("nan"), 100, 0, 2),
        (0, float("nan"), 0, 2),
        (True, 100, 0, 2),
        (0, "100", 0, 2),
        (0, 100, -1, 2),
        (0, 100, True, 2),
        (0, 100, 0, 0),
        (0, 100, 0, True),
        (0, 100, 0, 1.5),
    ],
)
async def test_sorted_set_query_rejects_invalid_arguments_before_io(minimum, maximum, offset, count) -> None:
    client = Mock(spec=Redis)
    client.zrangebyscore = AsyncMock()
    cache = ManagedRedisCacheClient(RedisStorage(client), CacheKeyBuilder("app"), default_ttl=None)
    with pytest.raises(ValueError):
        await cache.sorted_set_range_by_score("queue", minimum=minimum, maximum=maximum, offset=offset, count=count)
    client.zrangebyscore.assert_not_awaited()


@pytest.mark.asyncio
async def test_sorted_set_query_validates_key_before_io() -> None:
    client = Mock(spec=Redis)
    client.zrangebyscore = AsyncMock()
    cache = ManagedRedisCacheClient(RedisStorage(client), CacheKeyBuilder("app"), default_ttl=None)
    with pytest.raises(CacheKeyError):
        await cache.sorted_set_range_by_score("bad key", minimum=0, maximum=100, count=2)
    client.zrangebyscore.assert_not_awaited()


@pytest.mark.asyncio
async def test_sorted_set_query_returns_empty_tuple_for_empty_range() -> None:
    client = Mock(spec=Redis)
    client.zrangebyscore = AsyncMock(return_value=[])
    cache = ManagedRedisCacheClient(RedisStorage(client), CacheKeyBuilder("app"), default_ttl=None)
    assert await cache.sorted_set_range_by_score("queue", minimum=0, maximum=100, count=2) == ()


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", [None, (b"u",), ["u"], [b"u", 1]])
async def test_sorted_set_query_rejects_invalid_driver_result(raw) -> None:
    client = Mock(spec=Redis)
    client.zrangebyscore = AsyncMock(return_value=raw)
    cache = ManagedRedisCacheClient(RedisStorage(client), CacheKeyBuilder("app"), default_ttl=None)
    with pytest.raises(CacheOperationError) as captured:
        await cache.sorted_set_range_by_score("queue", minimum=0, maximum=100, count=2)
    assert isinstance(captured.value.__cause__, TypeError)


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_sorted_set_query_translates_driver_errors_but_preserves_cancellation(cancel: bool) -> None:
    import asyncio

    from redis.exceptions import ResponseError

    error = asyncio.CancelledError() if cancel else ResponseError("invalid state")
    client = Mock(spec=Redis)
    client.zrangebyscore = AsyncMock(side_effect=error)
    cache = ManagedRedisCacheClient(RedisStorage(client), CacheKeyBuilder("app"), default_ttl=None)
    with pytest.raises(asyncio.CancelledError if cancel else CacheOperationError) as captured:
        await cache.sorted_set_range_by_score("queue", minimum=0, maximum=100, count=2)
    if cancel:
        assert captured.value is error
    else:
        assert captured.value.__cause__ is error


@pytest.mark.asyncio
async def test_sorted_set_query_logs_safe_driver_error(caplog: pytest.LogCaptureFixture) -> None:
    from redis.exceptions import ResponseError

    client = Mock(spec=Redis)
    client.zrangebyscore = AsyncMock(side_effect=ResponseError("secret response"))
    cache = ManagedRedisCacheClient(RedisStorage(client), CacheKeyBuilder("app"), default_ttl=None)

    with caplog.at_level(logging.ERROR, logger="app.infrastructure.cache"), pytest.raises(CacheOperationError):
        await cache.sorted_set_range_by_score("queue", minimum=0, maximum=100, count=2)

    record = next(item for item in caplog.records if item.getMessage() == "Redis Sorted Set 查询失败")
    details = getattr(record, "details", {})
    assert getattr(record, "event", None) == "cache.operation.failed"
    assert isinstance(details, dict)
    assert details["operation"] == "sorted_set.range_by_score"
    assert details["error_type"] == "redis.exceptions.ResponseError"
    assert "secret response" not in str(details)


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


@pytest.mark.asyncio
async def test_redis_data_type_operations_preserve_bytes_prefix_and_explicit_options() -> None:
    driver = Mock(spec=Redis)
    driver.hgetall = AsyncMock(return_value={b"token": b"10"})
    driver.hset = AsyncMock(return_value=0)
    driver.sadd = AsyncMock(side_effect=[1, 0])
    driver.zadd = AsyncMock(side_effect=[1, 0])
    driver.zrem = AsyncMock(side_effect=[1, 0])
    driver.set = AsyncMock(side_effect=[True, None])
    cache = ManagedRedisCacheClient(RedisStorage(driver), CacheKeyBuilder("app", "shared"), default_ttl=999)

    assert await cache.hash_get_all("balance") == {b"token": b"10"}
    assert await cache.hash_set("balance", {"token": b"9"}) == 0
    assert await cache.set_add("dedupe", b"r") is True
    assert await cache.set_add("dedupe", b"r") is False
    assert await cache.sorted_set_add("queue", b"u", score=100, nx=True) is True
    assert await cache.sorted_set_add("queue", b"u", score=160) is False
    assert await cache.sorted_set_remove("queue", b"u") is True
    assert await cache.sorted_set_remove("queue", b"u") is False
    assert await cache.set_if_absent("lock", b"owner", ttl_ms=30000) is True
    assert await cache.set_if_absent("lock", b"other", ttl_ms=30000) is False

    driver.hgetall.assert_awaited_once_with("app:shared:balance")
    driver.hset.assert_awaited_once_with("app:shared:balance", mapping={"token": b"9"})
    driver.sadd.assert_awaited_with("app:shared:dedupe", b"r")
    driver.zadd.assert_any_await("app:shared:queue", {b"u": 100}, nx=True)
    driver.zadd.assert_any_await("app:shared:queue", {b"u": 160}, nx=False)
    driver.zrem.assert_awaited_with("app:shared:queue", b"u")
    driver.set.assert_any_await("app:shared:lock", b"owner", nx=True, px=30000)
    driver.eval.assert_not_called()
    driver.expire.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,args,kwargs,error_type",
    [
        ("hash_get_all", ("bad key",), {}, CacheKeyError),
        ("hash_set", ("key", {}), {}, ValueError),
        ("hash_set", ("key", {"token": "1"}), {}, TypeError),
        ("hash_set", ("key", {"": b"1"}), {}, TypeError),
        ("set_add", ("key", "r"), {}, TypeError),
        ("sorted_set_add", ("key", "u"), {"score": 100}, TypeError),
        ("sorted_set_add", ("key", b"u"), {"score": float("nan")}, ValueError),
        ("sorted_set_add", ("key", b"u"), {"score": True}, ValueError),
        ("sorted_set_add", ("key", b"u"), {"score": 100, "nx": 1}, TypeError),
        ("sorted_set_remove", ("key", "u"), {}, TypeError),
        ("set_if_absent", ("key", "owner"), {"ttl_ms": 30000}, TypeError),
        ("set_if_absent", ("key", b"owner"), {"ttl_ms": 0}, ValueError),
        ("set_if_absent", ("key", b"owner"), {"ttl_ms": True}, ValueError),
    ],
)
async def test_redis_data_type_operations_validate_before_io(method, args, kwargs, error_type) -> None:
    driver = Mock(spec=Redis)
    cache = ManagedRedisCacheClient(RedisStorage(driver), CacheKeyBuilder("app"), default_ttl=None)
    with pytest.raises(error_type):
        await getattr(cache, method)(*args, **kwargs)
    assert driver.mock_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,args,kwargs,driver_method,invalid_result",
    [
        ("hash_get_all", ("key",), {}, "hgetall", {"token": b"1"}),
        ("hash_get_all", ("key",), {}, "hgetall", {b"token": "1"}),
        ("hash_get_all", ("key",), {}, "hgetall", []),
        ("hash_set", ("key", {"token": b"1"}), {}, "hset", -1),
        ("set_add", ("key", b"r"), {}, "sadd", True),
        ("sorted_set_add", ("key", b"u"), {"score": 100}, "zadd", None),
        ("sorted_set_remove", ("key", b"u"), {}, "zrem", 2),
        ("set_if_absent", ("key", b"owner"), {"ttl_ms": 30000}, "set", "OK"),
    ],
)
async def test_redis_data_type_operations_reject_invalid_driver_results(method, args, kwargs, driver_method, invalid_result) -> None:
    driver = Mock(spec=Redis)
    setattr(driver, driver_method, AsyncMock(return_value=invalid_result))
    cache = ManagedRedisCacheClient(RedisStorage(driver), CacheKeyBuilder("app"), default_ttl=None)
    with pytest.raises(CacheOperationError) as caught:
        await getattr(cache, method)(*args, **kwargs)
    assert isinstance(caught.value.__cause__, TypeError)


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
@pytest.mark.parametrize(
    "method,args,kwargs,driver_method",
    [
        ("hash_get_all", ("key",), {}, "hgetall"),
        ("hash_set", ("key", {"token": b"1"}), {}, "hset"),
        ("set_add", ("key", b"r"), {}, "sadd"),
        ("sorted_set_add", ("key", b"u"), {"score": 100}, "zadd"),
        ("sorted_set_remove", ("key", b"u"), {}, "zrem"),
        ("set_if_absent", ("key", b"owner"), {"ttl_ms": 30000}, "set"),
    ],
)
async def test_redis_data_type_operations_translate_errors_and_preserve_cancellation(method, args, kwargs, driver_method, cancel: bool) -> None:
    import asyncio

    from redis.exceptions import ResponseError

    error = asyncio.CancelledError() if cancel else ResponseError("unavailable")
    driver = Mock(spec=Redis)
    setattr(driver, driver_method, AsyncMock(side_effect=error))
    cache = ManagedRedisCacheClient(RedisStorage(driver), CacheKeyBuilder("app"), default_ttl=None)
    with pytest.raises(asyncio.CancelledError if cancel else CacheOperationError) as caught:
        await getattr(cache, method)(*args, **kwargs)
    assert caught.value is error if cancel else caught.value.__cause__ is error
