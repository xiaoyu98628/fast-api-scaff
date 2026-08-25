from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.infrastructure.cache.backends.memory import MemoryCacheBackend
from app.infrastructure.cache.contracts.backend import CacheBackend
from app.infrastructure.cache.contracts.provider import CacheBackendDefinition


class MemoryCacheSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    driver: Literal["memory"]
    key_prefix: str = ""


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
