"""提供 Redis 数据类型 Storage 共用的客户端引用。"""

from redis.asyncio import Redis


class BaseRedisStorage:
    """保存由 Redis 连接资源拥有的异步客户端。"""

    def __init__(self, client: Redis) -> None:
        """借用客户端；连接建立、健康检查和关闭仍由 Connection 负责。"""

        self._client = client
