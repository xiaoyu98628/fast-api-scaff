"""维护缓存 driver 到 Provider 的显式映射。"""

from collections.abc import Iterable

from app.infrastructure.cache.contracts.provider import CacheProvider, CacheResourceDefinition
from app.infrastructure.cache.errors import CacheConfigurationError
from app.infrastructure.cache.providers.memcached import MemcachedCacheProvider
from app.infrastructure.cache.providers.redis import RedisCacheProvider


class CacheProviderRegistry:
    """显式注册并按 driver 查找缓存 Provider。"""

    def __init__(self, providers: Iterable[CacheProvider]) -> None:
        """注册 Provider，并拒绝空名称或重复的 driver。"""

        self._providers: dict[str, CacheProvider] = {}

        # 构建时拒绝空名称和重复注册，使运行期选择保持确定性。
        for provider in providers:
            if not provider.driver:
                raise CacheConfigurationError("缓存 Provider 的 driver 不能为空")

            if provider.driver in self._providers:
                raise CacheConfigurationError(f"缓存驱动 {provider.driver!r} 重复注册")

            self._providers[provider.driver] = provider

    @property
    def drivers(self) -> tuple[str, ...]:
        """返回当前注册的全部 driver 名称。"""

        return tuple(self._providers)

    def prepare(self, raw_config: dict[str, object]) -> CacheResourceDefinition:
        """按原始配置中的 driver 选择 Provider 并完成严格校验。"""

        driver = raw_config.get("driver")
        if not isinstance(driver, str) or not driver:
            raise CacheConfigurationError("缓存连接没有配置有效的 driver")

        provider = self._providers.get(driver)
        if provider is None:
            raise CacheConfigurationError(f"不支持缓存驱动 {driver!r}")

        return provider.prepare(raw_config)

    def extended(self, *providers: CacheProvider) -> CacheProviderRegistry:
        """返回包含额外 Provider 的新注册表，不修改默认实例。"""

        return CacheProviderRegistry((*self._providers.values(), *providers))


DEFAULT_CACHE_PROVIDERS = CacheProviderRegistry(
    (
        RedisCacheProvider(),
        MemcachedCacheProvider(),
    )
)
