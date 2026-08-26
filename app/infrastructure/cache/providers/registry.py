from collections.abc import Iterable

from app.infrastructure.cache.contracts.provider import CacheProvider, CacheResourceDefinition
from app.infrastructure.cache.errors import CacheConfigurationError
from app.infrastructure.cache.providers.memcached import MemcachedCacheProvider
from app.infrastructure.cache.providers.memory import MemoryCacheProvider
from app.infrastructure.cache.providers.redis import RedisCacheProvider


class CacheProviderRegistry:
    """显式注册并按 driver 查找缓存 Provider。"""

    def __init__(self, providers: Iterable[CacheProvider]) -> None:
        self._providers: dict[str, CacheProvider] = {}

        for provider in providers:
            if not provider.driver:
                raise CacheConfigurationError("缓存 Provider 的 driver 不能为空")

            if provider.driver in self._providers:
                raise CacheConfigurationError(f"缓存驱动 {provider.driver!r} 重复注册")

            self._providers[provider.driver] = provider

    @property
    def drivers(self) -> tuple[str, ...]:
        return tuple(self._providers)

    def prepare(self, raw_config: dict[str, object]) -> CacheResourceDefinition:
        driver = raw_config.get("driver")
        if not isinstance(driver, str) or not driver:
            raise CacheConfigurationError("缓存连接没有配置有效的 driver")

        provider = self._providers.get(driver)
        if provider is None:
            raise CacheConfigurationError(f"不支持缓存驱动 {driver!r}")

        return provider.prepare(raw_config)

    def extended(self, *providers: CacheProvider) -> CacheProviderRegistry:
        return CacheProviderRegistry((*self._providers.values(), *providers))


DEFAULT_CACHE_PROVIDERS = CacheProviderRegistry(
    (
        RedisCacheProvider(),
        MemcachedCacheProvider(),
        MemoryCacheProvider(),
    )
)
