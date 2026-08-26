from functools import partial

from app.config.cache import MemcachedCacheSettings
from app.infrastructure.cache.connections.memcached import MemcachedCacheConnection
from app.infrastructure.cache.contracts.provider import CacheResourceDefinition
from app.infrastructure.cache.resource import CacheResource
from app.infrastructure.cache.storages.memcached import MemcachedCacheStorage


class MemcachedCacheProvider:
    driver = "memcached"

    def prepare(self, raw_config: dict[str, object]) -> CacheResourceDefinition:
        settings = MemcachedCacheSettings.model_validate(raw_config)
        return CacheResourceDefinition(
            key_prefix=settings.key_prefix,
            factory=partial(self._create, settings),
        )

    async def _create(self, settings: MemcachedCacheSettings) -> CacheResource:
        connection = MemcachedCacheConnection.from_settings(settings)
        return CacheResource(
            connection=connection,
            storage=MemcachedCacheStorage(connection.client),
        )
