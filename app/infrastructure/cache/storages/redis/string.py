"""将 Redis String 命令适配为统一字节级 KV Storage。"""

from pathlib import Path

from redis.asyncio import Redis

from app.infrastructure.cache.errors import CacheOperationError
from app.infrastructure.cache.storages.redis.base import BaseRedisStorage

# 按模块位置定位资源，首次导入时读取一次，避免依赖工作目录或在请求中读取文件。
_SCRIPT_DIRECTORY = Path(__file__).parent / "scripts"
_INCREMENT_WITH_TTL_SCRIPT = (_SCRIPT_DIRECTORY / "increment_with_ttl.lua").read_text(encoding="utf-8")
_ACQUIRE_WINDOW_SCRIPT = (_SCRIPT_DIRECTORY / "acquire_window.lua").read_text(encoding="utf-8")


class RedisStringStorage(BaseRedisStorage):
    """实现 Redis String 对应的字节级 KV 操作。"""

    def __init__(self, client: Redis) -> None:
        """借用连接资源拥有的 Redis 客户端，不接管其生命周期。"""

        super().__init__(client)

    async def acquire_window(self, key: str, limit: int, window_ms: int) -> tuple[bool, int]:
        """原子消耗配额；拒绝不续期，驱动错误与无效状态转换为缓存操作异常。"""

        try:
            result = await self._client.eval(_ACQUIRE_WINDOW_SCRIPT, 1, key, limit, window_ms)
        except Exception as error:
            raise CacheOperationError("Redis 固定窗口配额操作失败") from error

        if not isinstance(result, (list, tuple)) or len(result) != 2:
            raise CacheOperationError("Redis 返回了无效的配额结果")
        allowed, ttl = result
        if type(allowed) is not int or allowed not in (0, 1) or type(ttl) is not int or not 0 <= ttl <= window_ms or (allowed == 1 and ttl != 0):
            raise CacheOperationError("Redis 返回了无效的配额状态")
        return bool(allowed), ttl

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

    async def delete(self, key: str) -> bool:
        """删除 key，并按受影响数量返回是否存在。"""

        try:
            return await self._client.delete(key) > 0
        except Exception as error:
            raise CacheOperationError("Redis 删除缓存失败") from error

    async def exists(self, key: str) -> bool:
        """使用 Redis EXISTS 判断 key 是否存在。"""

        try:
            return await self._client.exists(key) > 0
        except Exception as error:
            raise CacheOperationError("Redis 检查缓存失败") from error

    async def increment(self, key: str, ttl: int) -> int:
        """原子递增整数，并只在首次创建 key 时设置过期时间。"""

        try:
            value = await self._client.eval(_INCREMENT_WITH_TTL_SCRIPT, 1, key, ttl)
        except Exception as error:
            raise CacheOperationError("Redis 原子递增缓存失败") from error

        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise CacheOperationError("Redis 返回了无效的递增结果")

        return value

    async def expire(self, key: str, ttl: int) -> bool:
        """更新已有 key 的秒级过期时间。"""

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
