from redis.asyncio import Redis

from app.infrastructure.cache.errors import CacheOperationError
from app.infrastructure.cache.storages.redis.base import BaseRedisStorage


class RedisStringStorage(BaseRedisStorage):
    """实现 Redis String 对应的字节级 KV 操作。"""

    def __init__(self, client: Redis) -> None:
        super().__init__(client)

    async def get(self, key: str) -> bytes | None:
        try:
            value = await self._client.get(key)
        except Exception as error:
            raise CacheOperationError("Redis 读取缓存失败") from error

        if value is None or isinstance(value, bytes):
            return value

        raise CacheOperationError("Redis 返回了非 bytes 类型的缓存值")

    async def set(self, key: str, value: bytes, ttl: int | None) -> bool:
        try:
            result = await self._client.set(key, value, ex=ttl)
        except Exception as error:
            raise CacheOperationError("Redis 写入缓存失败") from error

        return result is True

    async def delete(self, key: str) -> bool:
        try:
            return await self._client.delete(key) > 0
        except Exception as error:
            raise CacheOperationError("Redis 删除缓存失败") from error

    async def exists(self, key: str) -> bool:
        try:
            return await self._client.exists(key) > 0
        except Exception as error:
            raise CacheOperationError("Redis 检查缓存失败") from error
