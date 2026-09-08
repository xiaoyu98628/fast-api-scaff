"""保存所有 Redis 数据类型 Storage 共用的原生客户端。"""

from redis.asyncio import Redis


class BaseRedisStorage:
    """保存 Redis Storage 共用的原生客户端。"""

    def __init__(self, client: Redis) -> None:
        self._client = client
