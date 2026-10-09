"""通过借用的 Redis 连接查询和写入 Sorted Set 成员。"""

import logging

from app.infrastructure.cache.errors import CacheOperationError
from app.infrastructure.cache.storages.redis.base import BaseRedisStorage
from app.infrastructure.logging.record import log_extra, safe_exception_details

_logger = logging.getLogger("app.infrastructure.cache")


class RedisSortedSetStorage(BaseRedisStorage):
    """处理有序集合字节成员，不解释分数或成员的业务含义。"""

    async def add(self, key: str, member: bytes, score: int | float, *, nx: bool) -> bool:
        """写入单个成员，nx 为真时不更新已有成员，返回是否新增。"""
        try:
            result = await self._client.zadd(key, {member: score}, nx=nx)
            if type(result) is not int or result not in (0, 1):
                raise TypeError("Redis ZADD 返回了无效成员数")
            return result == 1
        except Exception as error:
            raise CacheOperationError("Redis 添加 Sorted Set 成员失败") from error

    async def remove(self, key: str, member: bytes) -> bool:
        """移除单个成员，返回成员是否存在；取消继续传播。"""
        try:
            result = await self._client.zrem(key, member)
            if type(result) is not int or result not in (0, 1):
                raise TypeError("Redis ZREM 返回了无效成员数")
            return result == 1
        except Exception as error:
            raise CacheOperationError("Redis 移除 Sorted Set 成员失败") from error

    async def range_by_score(self, key: str, minimum: int | float, maximum: int | float, *, offset: int, count: int) -> tuple[bytes, ...]:
        """读取包含上下界的分数范围，保持 Redis 返回顺序且不移除成员。"""
        try:
            raw = await self._client.zrangebyscore(key, minimum, maximum, start=offset, num=count)
            if not isinstance(raw, list):
                raise TypeError("Redis Sorted Set 返回了非字节成员列表")
            members: list[bytes] = []
            for member in raw:
                if not isinstance(member, bytes):
                    raise TypeError("Redis Sorted Set 返回了非字节成员列表")
                members.append(member)
            return tuple(members)
        except Exception as error:
            error_type, stacktrace = safe_exception_details(error)
            _logger.error(
                "Redis Sorted Set 查询失败",
                extra=log_extra(
                    "cache.operation.failed",
                    backend="redis",
                    operation="sorted_set.range_by_score",
                    error_type=error_type,
                    stacktrace=stacktrace,
                ),
            )
            raise CacheOperationError("Redis 查询 Sorted Set 失败") from error
