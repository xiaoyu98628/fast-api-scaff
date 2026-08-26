from functools import partial

from app.config.cache import RedisCacheSettings
from app.infrastructure.cache.connections.redis import RedisCacheConnection
from app.infrastructure.cache.contracts.provider import CacheResourceDefinition
from app.infrastructure.cache.resource import CacheResource
from app.infrastructure.cache.storages.redis.storage import RedisStorage


class RedisCacheProvider:
    driver = "redis"

    def prepare(self, raw_config: dict[str, object]) -> CacheResourceDefinition:
        settings = RedisCacheSettings.model_validate(raw_config)
        return CacheResourceDefinition(
            key_prefix=settings.key_prefix,
            factory=partial(self._create, settings),
        )

    async def _create(self, settings: RedisCacheSettings) -> CacheResource:
        connection = RedisCacheConnection.from_settings(settings)
        return CacheResource(
            connection=connection,
            storage=RedisStorage(connection.client),
        )
