"""保存所有 Redis 数据类型 Storage 共用的原生客户端。"""

from redis.asyncio import Redis


class BaseRedisStorage:
    """保存 Redis Storage 共用的原生客户端。"""

    def __init__(self, client: Redis) -> None:
        """保存由连接资源拥有的 Redis 客户端引用。"""

        self._client = client
