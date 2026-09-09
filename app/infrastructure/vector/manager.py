"""管理向量存储配置、命名连接和延迟客户端生命周期。"""

from anyio import CancelScope
from pydantic import ValidationError

from app.config.vector import VectorSettings
from app.infrastructure.resources.lazy import AsyncLazy
from app.infrastructure.vector.contracts.client import VectorClient
from app.infrastructure.vector.contracts.provider import VectorResourceDefinition
from app.infrastructure.vector.errors import VectorConfigurationError
from app.infrastructure.vector.providers.registry import DEFAULT_VECTOR_PROVIDERS, VectorProviderRegistry
from app.infrastructure.vector.resource import VectorResource


class VectorStoreManager:
    """按名称选择驱动并延迟管理本地或远程向量客户端。"""

    def __init__(
        self,
        settings: VectorSettings,
        providers: VectorProviderRegistry = DEFAULT_VECTOR_PROVIDERS,
    ) -> None:
        """严格校验全部配置，但不创建文件或连接外部服务。"""

        self._default = settings.default
        self._closed = False
        definitions = self._prepare_connections(settings, providers)
        self._resources = {
            name: AsyncLazy(
                factory=definition.factory,
                closer=VectorResource.aclose,
            )
            for name, definition in definitions.items()
        }

    @property
    def default_name(self) -> str | None:
        """返回默认连接名称，不初始化客户端。"""

        return self._default

    @property
    def connection_names(self) -> tuple[str, ...]:
        """返回声明顺序稳定的全部命名连接。"""

        return tuple(self._resources)

    def is_initialized(self, name: str | None = None) -> bool:
        """报告指定向量客户端是否已经创建。"""

        return self._resources[self._resolve_name(name)].initialized

    async def get(self, name: str | None = None) -> VectorClient:
        """延迟创建并返回指定连接的统一向量客户端。"""

        if self._closed:
            raise RuntimeError("向量存储管理器已经关闭")
        return (await self._resources[self._resolve_name(name)].get()).client

    async def ping(self, name: str | None = None) -> bool:
        """通过指定驱动的健康操作验证资源可访问性。"""

        return await (await self.get(name)).ping()

    async def aclose(self) -> None:
        """封锁新获取并释放全部已初始化向量资源。"""

        self._closed = True
        for resource in self._resources.values():
            resource.begin_close()

        errors: list[BaseException] = []
        with CancelScope(shield=True):
            for resource in reversed(tuple(self._resources.values())):
                try:
                    await resource.aclose()
                except BaseException as error:
                    errors.append(error)

        if errors:
            raise BaseExceptionGroup("向量存储资源关闭失败", errors)

    @staticmethod
    def _prepare_connections(
        settings: VectorSettings,
        providers: VectorProviderRegistry,
    ) -> dict[str, VectorResourceDefinition]:
        if settings.default is not None and settings.default not in settings.connections:
            raise VectorConfigurationError(f"默认向量连接 {settings.default!r} 未配置")

        definitions: dict[str, VectorResourceDefinition] = {}
        for name, raw_config in settings.connections.items():
            if not name.strip() or len(name) > 200:
                raise VectorConfigurationError("向量连接名不合法")
            try:
                definitions[name] = providers.prepare(raw_config)
            except (ValidationError, ValueError, VectorConfigurationError) as error:
                raise VectorConfigurationError(f"向量连接 {name!r} 配置不合法") from error
        return definitions

    def _resolve_name(self, name: str | None) -> str:
        resolved = self._default if name is None else name
        if resolved is None or resolved not in self._resources:
            raise VectorConfigurationError("向量连接未配置")
        return resolved
