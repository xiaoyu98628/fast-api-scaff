"""聚合 Redis 数据类型适配器并暴露通用 KV 接口。"""

from redis.asyncio import Redis

from app.infrastructure.cache.storages.redis.script import RedisScriptExecutor
from app.infrastructure.cache.storages.redis.string import RedisStringStorage


class RedisStorage:
    """聚合 Redis 数据类型存储，并以 String 提供通用 KV 能力。"""

    def __init__(self, client: Redis) -> None:
        """用同一个 Redis 客户端创建已实现的数据类型适配器。"""

        self.strings = RedisStringStorage(client)
        self.scripts = RedisScriptExecutor(client)

    async def get(self, key: str) -> bytes | None:
        """读取 bytes；拒绝客户端配置错误导致的文本返回值。"""

        return await self.strings.get(key)

    async def set(self, key: str, value: bytes, ttl: int | None) -> bool:
        """使用 Redis EX 秒级过期语义写入值。"""

        return await self.strings.set(key, value, ttl)

    async def delete(self, key: str) -> bool:
        """删除 key，并按受影响数量返回是否存在。"""

        return await self.strings.delete(key)

    async def exists(self, key: str) -> bool:
        """使用 Redis EXISTS 判断 key 是否存在。"""

        return await self.strings.exists(key)
