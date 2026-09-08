"""把 Redis 配置转换为延迟缓存资源定义。"""

from functools import partial

from app.config.cache import RedisCacheSettings
from app.infrastructure.cache.connections.redis import RedisCacheConnection
from app.infrastructure.cache.contracts.provider import CacheResourceDefinition
from app.infrastructure.cache.resource import CacheResource
from app.infrastructure.cache.storages.redis.storage import RedisStorage


class RedisCacheProvider:
    """校验 Redis 配置并装配连接与聚合 Storage。"""

    driver = "redis"

    def prepare(self, raw_config: dict[str, object]) -> CacheResourceDefinition:
        """生成尚未建立网络连接的资源定义。"""

        settings = RedisCacheSettings.model_validate(raw_config)
        return CacheResourceDefinition(
            key_prefix=settings.key_prefix,
            factory=partial(self._create, settings),
        )

    async def _create(self, settings: RedisCacheSettings) -> CacheResource:
        """构造共享同一原生客户端的连接和 Storage。"""

        connection = RedisCacheConnection.from_settings(settings)
        return CacheResource(
            connection=connection,
            storage=RedisStorage(connection.client),
        )
