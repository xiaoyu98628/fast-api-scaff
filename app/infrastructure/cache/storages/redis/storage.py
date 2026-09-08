"""聚合 Redis 数据类型适配器并暴露通用 KV 接口。"""

from redis.asyncio import Redis

from app.infrastructure.cache.storages.redis.string import RedisStringStorage


class RedisStorage:
    """聚合 Redis 数据类型存储，并以 String 提供通用 KV 能力。"""

    def __init__(self, client: Redis) -> None:
        """用同一个 Redis 客户端创建各数据类型适配器。"""

        # 保留数据类型分层，避免未来扩展 Hash/Set 时把协议细节堆入统一客户端。
        self.strings = RedisStringStorage(client)

    async def get(self, key: str) -> bytes | None:
        """通过 Redis String 读取字节值。"""

        return await self.strings.get(key)

    async def set(self, key: str, value: bytes, ttl: int | None) -> bool:
        """通过 Redis String 写入带可选秒级 TTL 的值。"""

        return await self.strings.set(key, value, ttl)

    async def delete(self, key: str) -> bool:
        """通过 Redis String 删除 key。"""

        return await self.strings.delete(key)

    async def exists(self, key: str) -> bool:
        """通过 Redis String 判断 key 是否存在。"""

        return await self.strings.exists(key)
