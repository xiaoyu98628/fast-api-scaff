from redis.asyncio import Redis

from app.infrastructure.cache.errors import CacheConnectionError, CacheOperationError


class RedisCacheBackend:
    def __init__(self, client: Redis) -> None:
        self._client = client

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

    async def ping(self) -> bool:
        try:
            return bool(await self._client.ping())
        except Exception as error:
            raise CacheConnectionError("Redis 健康检查失败") from error

    async def aclose(self) -> None:
        try:
            await self._client.aclose()
        except Exception as error:
            raise CacheConnectionError("Redis 客户端关闭失败") from error
