import pytest

from app.config.cache import CacheSettings
from app.infrastructure.cache.backends.memory import MemoryCacheBackend
from app.infrastructure.cache.contracts.backend import CacheBackend
from app.infrastructure.cache.contracts.provider import CacheBackendDefinition
from app.infrastructure.cache.errors import CacheConfigurationError
from app.infrastructure.cache.manager import CacheManager
from app.infrastructure.cache.providers.memory import MemoryCacheProvider
from app.infrastructure.cache.providers.registry import DEFAULT_CACHE_PROVIDERS, CacheProviderRegistry


class CustomCacheProvider:
    driver = "custom"

    def prepare(self, raw_config: dict[str, object]) -> CacheBackendDefinition:
        return CacheBackendDefinition(
            key_prefix=str(raw_config.get("key_prefix", "")),
            factory=self._create,
        )

    async def _create(self) -> CacheBackend:
        return MemoryCacheBackend()


def test_default_registry_contains_builtin_drivers() -> None:
    assert DEFAULT_CACHE_PROVIDERS.drivers == ("redis", "memcached", "memory")


def test_registry_rejects_duplicate_driver() -> None:
    with pytest.raises(CacheConfigurationError, match="重复注册"):
        CacheProviderRegistry((MemoryCacheProvider(), MemoryCacheProvider()))


@pytest.mark.parametrize("raw_config", [{}, {"driver": "unknown"}])
def test_registry_rejects_missing_or_unknown_driver(raw_config: dict[str, object]) -> None:
    with pytest.raises(CacheConfigurationError):
        DEFAULT_CACHE_PROVIDERS.prepare(raw_config)


@pytest.mark.asyncio
async def test_manager_accepts_extended_provider_registry() -> None:
    providers = DEFAULT_CACHE_PROVIDERS.extended(CustomCacheProvider())
    settings = CacheSettings(
        default="main",
        namespace="test",
        connections={"main": {"driver": "custom", "key_prefix": "custom"}},
        _env_file=None,
    )
    manager = CacheManager(settings, providers=providers)

    cache = await manager.get()
    await cache.set("key", b"value")

    assert await cache.get("key") == b"value"
    assert "custom" not in DEFAULT_CACHE_PROVIDERS.drivers
    await manager.aclose()
