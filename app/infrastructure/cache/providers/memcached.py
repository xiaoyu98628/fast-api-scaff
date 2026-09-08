"""把 Memcached 配置转换为延迟缓存资源定义。"""

from functools import partial

from app.config.cache import MemcachedCacheSettings
from app.infrastructure.cache.connections.memcached import MemcachedCacheConnection
from app.infrastructure.cache.contracts.provider import CacheResourceDefinition
from app.infrastructure.cache.resource import CacheResource
from app.infrastructure.cache.storages.memcached import MemcachedCacheStorage


class MemcachedCacheProvider:
    """校验 Memcached 配置并装配连接与字节 Storage。"""

    driver = "memcached"

    def prepare(self, raw_config: dict[str, object]) -> CacheResourceDefinition:
        """生成尚未连接外部服务的资源定义。"""

        settings = MemcachedCacheSettings.model_validate(raw_config)
        return CacheResourceDefinition(
            key_prefix=settings.key_prefix,
            factory=partial(self._create, settings),
        )

    async def _create(self, settings: MemcachedCacheSettings) -> CacheResource:
        """构造共享同一原生客户端的连接和 Storage。"""

        connection = MemcachedCacheConnection.from_settings(settings)
        return CacheResource(
            connection=connection,
            storage=MemcachedCacheStorage(connection.client),
        )
