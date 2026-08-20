from unittest.mock import AsyncMock, Mock

import pytest
from memcachio import Client, MemcachedItem
from redis.asyncio import Redis

from app.infrastructure.cache.backends.memcached_cache import MemcachedCache
from app.infrastructure.cache.backends.redis_cache import RedisCache


@pytest.mark.asyncio
async def test_redis_cache_applies_prefix_and_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Redis(host="127.0.0.1", decode_responses=False)
    set_value = AsyncMock(return_value=True)
    get_value = AsyncMock(return_value=b"value")
    close = AsyncMock()
    monkeypatch.setattr(client, "set", set_value)
    monkeypatch.setattr(client, "get", get_value)
    monkeypatch.setattr(client, "aclose", close)
    cache = RedisCache(client, key_prefix="session:")

    assert await cache.set("token", b"value", ttl=60) is True
    assert await cache.get("token") == b"value"
    await cache.aclose()

    set_value.assert_awaited_once_with("session:token", b"value", ex=60)
    get_value.assert_awaited_once_with("session:token")
    close.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_memcached_cache_applies_prefix_and_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    client: Client[bytes] = Client(
        ("127.0.0.1", 11211),
        username="user",
        password="secret",
        decode_responses=False,
    )
    cache_key = b"page:home"
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
    cache = MemcachedCache(client, key_prefix="page:")

    assert await cache.set("home", b"value", ttl=60) is True
    assert await cache.get("home") == b"value"
    await cache.aclose()

    set_value.assert_awaited_once_with(cache_key, b"value", expiry=60)
    get_value.assert_awaited_once_with(cache_key)
    close.assert_called_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize("ttl", [0, -1])
async def test_cache_rejects_non_positive_ttl(ttl: int) -> None:
    client = Redis(host="127.0.0.1", decode_responses=False)
    cache = RedisCache(client)

    with pytest.raises(ValueError, match="ttl"):
        await cache.set("key", b"value", ttl=ttl)

    await cache.aclose()
