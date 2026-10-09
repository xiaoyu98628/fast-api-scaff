"""通过借用的 Redis 连接执行通用 Key 操作。"""

from app.infrastructure.cache.errors import CacheOperationError
from app.infrastructure.cache.storages.redis.base import BaseRedisStorage


class RedisKeyStorage(BaseRedisStorage):
    """处理与值类型无关的删除、存在性和过期时间命令。"""

    async def delete(self, key: str) -> bool:
        """删除 key，并按受影响数量返回是否存在。"""
        try:
            return await self._client.delete(key) > 0
        except Exception as error:
            raise CacheOperationError("Redis 删除缓存失败") from error

    async def exists(self, key: str) -> bool:
        """判断任意 Redis key 是否存在。"""
        try:
            return await self._client.exists(key) > 0
        except Exception as error:
            raise CacheOperationError("Redis 检查缓存失败") from error

    async def expire(self, key: str, ttl: int) -> bool:
        """更新任意已有 key 的秒级过期时间。"""
        try:
            return bool(await self._client.expire(key, ttl))
        except Exception as error:
            raise CacheOperationError("Redis 更新缓存过期时间失败") from error

    async def ttl(self, key: str) -> int:
        """返回 Redis TTL 秒数，并保留 -1 与 -2 状态值。"""
        try:
            value = await self._client.ttl(key)
        except Exception as error:
            raise CacheOperationError("Redis 读取缓存过期时间失败") from error

        if not isinstance(value, int) or isinstance(value, bool) or value < -2:
            raise CacheOperationError("Redis 返回了无效的过期时间")
        return value
