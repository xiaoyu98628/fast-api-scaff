"""将 Redis String 命令适配为统一字节级 KV Storage。"""

from redis.asyncio import Redis

from app.infrastructure.cache.errors import CacheOperationError
from app.infrastructure.cache.storages.redis.base import BaseRedisStorage


class RedisStringStorage(BaseRedisStorage):
    """实现 Redis String 对应的字节级 KV 操作。"""

    def __init__(self, client: Redis) -> None:
        """借用连接资源拥有的 Redis 客户端，不接管其生命周期。"""

        super().__init__(client)

    async def get(self, key: str) -> bytes | None:
        """读取 bytes；拒绝客户端配置错误导致的文本返回值。"""

        try:
            value = await self._client.get(key)
        except Exception as error:
            raise CacheOperationError("Redis 读取缓存失败") from error

        if value is None or isinstance(value, bytes):
            return value

        raise CacheOperationError("Redis 返回了非 bytes 类型的缓存值")

    async def set(self, key: str, value: bytes, ttl: int | None) -> bool:
        """使用 Redis EX 秒级过期语义写入值。"""

        try:
            result = await self._client.set(key, value, ex=ttl)
        except Exception as error:
            raise CacheOperationError("Redis 写入缓存失败") from error

        return result is True

    async def set_if_absent(self, key: str, value: bytes, ttl_ms: int) -> bool:
        """以 NX 和毫秒 TTL 写入，已存在时返回 False，不接管租约策略。"""
        try:
            result = await self._client.set(key, value, nx=True, px=ttl_ms)
            if result is not True and result is not None:
                raise TypeError("Redis SET NX 返回了无效结果")
            return result is True
        except Exception as error:
            raise CacheOperationError("Redis 条件写入缓存失败") from error
