"""创建和关闭 Memcached 原生异步客户端。"""

import ssl

from memcachio import Client

from app.config.cache import MemcachedCacheSettings
from app.infrastructure.cache.errors import CacheConnectionError


class MemcachedCacheConnection:
    """创建并管理 Memcached 原生异步客户端。"""

    def __init__(self, client: Client[bytes]) -> None:
        """接管由调用方创建的 Memcached 客户端。"""

        self._client = client

    @classmethod
    def from_settings(cls, settings: MemcachedCacheSettings) -> MemcachedCacheConnection:
        """根据连接池、认证和 TLS 配置构造客户端。"""

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
        """暴露给 Memcached Storage 使用的原生客户端。"""

        return self._client

    async def ping(self) -> bool:
        """通过 version 命令验证服务可访问。"""

        try:
            return bool(await self._client.version())
        except Exception as error:
            raise CacheConnectionError("Memcached 健康检查失败") from error

    async def aclose(self) -> None:
        """关闭原生连接池，并转换为稳定连接错误。"""

        try:
            self._client.connection_pool.close()
        except Exception as error:
            raise CacheConnectionError("Memcached 客户端关闭失败") from error
