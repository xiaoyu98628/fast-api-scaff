"""维护向量 driver 到 Provider 的显式映射。"""

from collections.abc import Iterable

from app.infrastructure.vector.contracts.provider import VectorProvider, VectorResourceDefinition
from app.infrastructure.vector.drivers.chroma import ChromaVectorProvider
from app.infrastructure.vector.drivers.elasticsearch import ElasticsearchVectorProvider
from app.infrastructure.vector.drivers.milvus import MilvusVectorProvider
from app.infrastructure.vector.errors import VectorConfigurationError


class VectorProviderRegistry:
    """注册并按 driver 查找向量 Provider。"""

    def __init__(self, providers: Iterable[VectorProvider]) -> None:
        """拒绝空名称和重复 driver，使选择结果保持确定。"""

        self._providers: dict[str, VectorProvider] = {}
        for provider in providers:
            if not provider.driver:
                raise VectorConfigurationError("向量 Provider 的 driver 不能为空")
            if provider.driver in self._providers:
                raise VectorConfigurationError(f"向量驱动 {provider.driver!r} 重复注册")
            self._providers[provider.driver] = provider

    @property
    def drivers(self) -> tuple[str, ...]:
        """返回已注册的 driver 名称。"""

        return tuple(self._providers)

    def prepare(self, raw_config: dict[str, object]) -> VectorResourceDefinition:
        """选择 Provider，并完成严格配置校验。"""

        driver = raw_config.get("driver")
        if not isinstance(driver, str) or not driver:
            raise VectorConfigurationError("向量连接没有配置有效的 driver")
        provider = self._providers.get(driver)
        if provider is None:
            raise VectorConfigurationError(f"不支持向量驱动 {driver!r}")
        return provider.prepare(raw_config)

    def extended(self, *providers: VectorProvider) -> VectorProviderRegistry:
        """返回包含额外 Provider 的新注册表，不修改默认实例。"""

        return VectorProviderRegistry((*self._providers.values(), *providers))


DEFAULT_VECTOR_PROVIDERS = VectorProviderRegistry(
    (
        MilvusVectorProvider(),
        ChromaVectorProvider(),
        ElasticsearchVectorProvider(),
    )
)
