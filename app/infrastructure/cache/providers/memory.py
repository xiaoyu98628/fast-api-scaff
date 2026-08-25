from app.config.cache import MemoryCacheSettings
from app.infrastructure.cache.backends.memory import MemoryCacheBackend
from app.infrastructure.cache.contracts.backend import CacheBackend
from app.infrastructure.cache.contracts.provider import CacheBackendDefinition


class MemoryCacheProvider:
    driver = "memory"

    def prepare(self, raw_config: dict[str, object]) -> CacheBackendDefinition:
        settings = MemoryCacheSettings.model_validate(raw_config)
        return CacheBackendDefinition(
            key_prefix=settings.key_prefix,
            factory=self._create,
        )

    async def _create(self) -> CacheBackend:
        return MemoryCacheBackend()
