from redis.asyncio import Redis

from app.config.cache import RedisCacheSettings
from app.infrastructure.cache.errors import CacheConnectionError


class RedisCacheConnection:
    """创建并管理 Redis 原生异步客户端。"""

    def __init__(self, client: Redis) -> None:
        self._client = client

    @classmethod
    def from_settings(cls, settings: RedisCacheSettings) -> RedisCacheConnection:
        client = Redis(
            host=settings.host,
            port=settings.port,
            db=settings.database,
            username=settings.username,
            password=settings.password.get_secret_value() if settings.password is not None else None,
            ssl=settings.ssl,
            max_connections=settings.max_connections,
            socket_connect_timeout=settings.connect_timeout,
            socket_timeout=settings.read_timeout,
            decode_responses=False,
        )
        return cls(client)

    @property
    def client(self) -> Redis:
        return self._client

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
