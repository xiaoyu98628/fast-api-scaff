"""通过借用的 Redis 连接添加 Set 字节成员。"""

from app.infrastructure.cache.errors import CacheOperationError
from app.infrastructure.cache.storages.redis.base import BaseRedisStorage


class RedisSetStorage(BaseRedisStorage):
    """提供单成员 SADD，不附加过期或业务去重策略。"""

    async def add(self, key: str, member: bytes) -> bool:
        """成员首次加入返回 True，已存在返回 False；取消继续传播。"""
        try:
            result = await self._client.sadd(key, member)
            if type(result) is not int or result not in (0, 1):
                raise TypeError("Redis SADD 返回了无效成员数")
            return result == 1
        except Exception as error:
            raise CacheOperationError("Redis 添加 Set 成员失败") from error
