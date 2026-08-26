import ssl

from memcachio import Client

from app.config.cache import MemcachedCacheSettings
from app.infrastructure.cache.errors import CacheConnectionError


class MemcachedCacheConnection:
    """创建并管理 Memcached 原生异步客户端。"""

    def __init__(self, client: Client[bytes]) -> None:
        self._client = client

    @classmethod
    def from_settings(cls, settings: MemcachedCacheSettings) -> MemcachedCacheConnection:
        ssl_context = ssl.create_default_context() if settings.ssl else None
        client: Client[bytes] = Client(
            (settings.host, settings.port),
            decode_responses=False,
            username=settings.username,
            password=settings.password.get_secret_value() if settings.password is not None else None,
            ssl_context=ssl_context,
            min_connections=settings.min_connections,
            max_connections=settings.max_connections,
            connect_timeout=settings.connect_timeout,
            read_timeout=settings.read_timeout,
            blocking_timeout=settings.blocking_timeout,
        )
        return cls(client)

    @property
    def client(self) -> Client[bytes]:
        return self._client

    async def ping(self) -> bool:
        try:
            return bool(await self._client.version())
        except Exception as error:
            raise CacheConnectionError("Memcached 健康检查失败") from error

    async def aclose(self) -> None:
        try:
            self._client.connection_pool.close()
        except Exception as error:
            raise CacheConnectionError("Memcached 客户端关闭失败") from error
