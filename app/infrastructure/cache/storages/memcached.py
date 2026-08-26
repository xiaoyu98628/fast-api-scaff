import time

from memcachio import Client

from app.infrastructure.cache.errors import CacheOperationError

MEMCACHED_RELATIVE_EXPIRY_LIMIT = 60 * 60 * 24 * 30


class MemcachedCacheStorage:
    """通过 Memcached 客户端实现字节级 KV 存储。"""

    def __init__(self, client: Client[bytes]) -> None:
        self._client = client

    async def get(self, key: str) -> bytes | None:
        cache_key = key.encode()
        try:
            items = await self._client.get(cache_key)
        except Exception as error:
            raise CacheOperationError("Memcached 读取缓存失败") from error

        item = items.get(cache_key)
        return item.value if item is not None else None

    async def set(self, key: str, value: bytes, ttl: int | None) -> bool:
        try:
            result = await self._client.set(key.encode(), value, expiry=self._expiry(ttl))
        except Exception as error:
            raise CacheOperationError("Memcached 写入缓存失败") from error

        return result is True

    async def delete(self, key: str) -> bool:
        try:
            result = await self._client.delete(key.encode())
        except Exception as error:
            raise CacheOperationError("Memcached 删除缓存失败") from error

        return result is True

    async def exists(self, key: str) -> bool:
        return await self.get(key) is not None

    @staticmethod
    def _expiry(ttl: int | None) -> int:
        if ttl is None:
            return 0

        if ttl <= MEMCACHED_RELATIVE_EXPIRY_LIMIT:
            return ttl

        return int(time.time()) + ttl
