from redis.asyncio import Redis

from app.platform.cache.backends.base import BaseCache


class RedisCache(BaseCache):
    def __init__(self, client: Redis, key_prefix: str = "") -> None:
        super().__init__(key_prefix)
        self._client = client

    async def get(self, key: str) -> bytes | None:
        value = await self._client.get(self._prefixed_key(key))

        if value is None or isinstance(value, bytes):
            return value

        raise TypeError("Redis 返回了非 bytes 类型的缓存值")

    async def set(self, key: str, value: bytes, ttl: int | None = None) -> bool:
        self._validate_ttl(ttl)
        result = await self._client.set(self._prefixed_key(key), value, ex=ttl)
        return result is True

    async def delete(self, key: str) -> bool:
        return await self._client.delete(self._prefixed_key(key)) > 0

    async def exists(self, key: str) -> bool:
        return await self._client.exists(self._prefixed_key(key)) > 0

    async def ping(self) -> bool:
        return bool(await self._client.ping())

    async def aclose(self) -> None:
        await self._client.aclose()
