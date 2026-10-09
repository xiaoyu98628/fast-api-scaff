"""通过借用的 Redis 连接读写 Hash 字节字段。"""

from redis.typing import EncodableT, FieldT

from app.infrastructure.cache.errors import CacheOperationError
from app.infrastructure.cache.storages.redis.base import BaseRedisStorage


class RedisHashStorage(BaseRedisStorage):
    """处理 Hash 驱动返回值，不解释字段的业务含义。"""

    async def get_all(self, key: str) -> dict[bytes, bytes]:
        """读取全部字节字段，缺失时返回空字典；驱动错误转换为缓存异常。"""
        try:
            raw = await self._client.hgetall(key)
            if not isinstance(raw, dict):
                raise TypeError("Redis Hash 返回了非字典结果")
            fields: dict[bytes, bytes] = {}
            for field, value in raw.items():
                if not isinstance(field, bytes) or not isinstance(value, bytes):
                    raise TypeError("Redis Hash 返回了非字节字段或值")
                fields[field] = value
            return fields
        except Exception as error:
            raise CacheOperationError("Redis 读取 Hash 失败") from error

    async def set(self, key: str, mapping: dict[str, bytes]) -> int:
        """写入指定字段，返回新增字段数，不替换未指定的字段或 TTL。"""
        try:
            fields: dict[FieldT, EncodableT] = {field: value for field, value in mapping.items()}
            result = await self._client.hset(key, mapping=fields)
            if type(result) is not int or result < 0:
                raise TypeError("Redis HSET 返回了无效字段数")
            return result
        except Exception as error:
            raise CacheOperationError("Redis 写入 Hash 失败") from error
