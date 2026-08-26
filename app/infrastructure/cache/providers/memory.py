from app.config.cache import MemoryCacheSettings
from app.infrastructure.cache.connections.memory import MemoryCacheConnection
from app.infrastructure.cache.contracts.provider import CacheResourceDefinition
from app.infrastructure.cache.resource import CacheResource
from app.infrastructure.cache.storages.memory import MemoryCacheStorage


class MemoryCacheProvider:
    driver = "memory"

    def prepare(self, raw_config: dict[str, object]) -> CacheResourceDefinition:
        settings = MemoryCacheSettings.model_validate(raw_config)
        return CacheResourceDefinition(
            key_prefix=settings.key_prefix,
            factory=self._create,
        )

    async def _create(self) -> CacheResource:
        connection = MemoryCacheConnection()
        return CacheResource(
            connection=connection,
            storage=MemoryCacheStorage(connection),
        )
