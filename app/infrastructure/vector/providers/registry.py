"""维护向量 driver 到 Provider 的显式映射。"""

from collections.abc import Iterable
from functools import partial

from app.config.vector import (
    ChromaLocalVectorSettings,
    ChromaRemoteVectorSettings,
    ElasticsearchVectorSettings,
    MilvusLocalVectorSettings,
    MilvusRemoteVectorSettings,
    VectorConnectionSettings,
    parse_vector_connection,
)
from app.infrastructure.vector.contracts.provider import VectorProvider, VectorResourceDefinition
from app.infrastructure.vector.errors import VectorConfigurationError
from app.infrastructure.vector.resource import VectorResource


class BuiltinVectorProvider:
    """校验内置驱动配置，并把具体驱动模块推迟到资源创建阶段。"""

    def __init__(self, driver: str) -> None:
        """保存该 Provider 唯一负责的驱动名称。"""

        self.driver = driver

    def prepare(self, raw_config: dict[str, object]) -> VectorResourceDefinition:
        """严格校验配置并返回按需导入驱动的资源工厂。"""

        settings = parse_vector_connection(raw_config)
        if settings.driver != self.driver:
            raise ValueError(f"配置不是 {self.driver} 连接")
        return VectorResourceDefinition(factory=partial(_create_builtin_resource, settings))


async def _create_builtin_resource(settings: VectorConnectionSettings) -> VectorResource:
    """只导入当前命名连接实际使用的向量驱动模块。"""

    try:
        match settings:
            case MilvusLocalVectorSettings() | MilvusRemoteVectorSettings():
                from app.infrastructure.vector.drivers.milvus import create_milvus_resource

                return await create_milvus_resource(settings)
            case ChromaLocalVectorSettings() | ChromaRemoteVectorSettings():
                from app.infrastructure.vector.drivers.chroma import create_chroma_resource

                return await create_chroma_resource(settings)
            case ElasticsearchVectorSettings():
                from app.infrastructure.vector.drivers.elasticsearch import create_elasticsearch_resource

                return await create_elasticsearch_resource(settings)
    except ModuleNotFoundError as error:
        raise VectorConfigurationError(f"向量驱动 {settings.driver!r} 的客户端依赖无法加载") from error

    raise AssertionError(f"未知向量连接配置类型: {type(settings)!r}")


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
        BuiltinVectorProvider("milvus"),
        BuiltinVectorProvider("chroma"),
        BuiltinVectorProvider("elasticsearch"),
    )
)
