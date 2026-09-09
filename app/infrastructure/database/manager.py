"""按连接名管理数据库配置、延迟资源和 Session 生命周期。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from copy import deepcopy
from functools import partial

from anyio import CancelScope
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.config.database import DatabaseSettings
from app.infrastructure.database.connections.resolver import validate_database_definition
from app.infrastructure.database.errors import DatabaseConfigurationError
from app.infrastructure.database.factory import close_database_resource, create_database_resource
from app.infrastructure.database.providers.registry import DEFAULT_DATABASE_PROVIDERS, DatabaseProviderRegistry
from app.infrastructure.database.resource import DatabaseResource
from app.infrastructure.resources.lazy import AsyncLazy


class DatabaseManager:
    """按名称管理延迟校验、延迟创建的数据库资源。"""

    def __init__(
        self,
        settings: DatabaseSettings,
        providers: DatabaseProviderRegistry = DEFAULT_DATABASE_PROVIDERS,
    ) -> None:
        """保存命名配置，并为每个连接建立延迟数据库资源。"""

        self._default = settings.default
        self._closed = False
        self._providers = providers
        # 数据库定义延迟到首次使用才解析，因此需与调用方仍可修改的原始字典隔离。
        connections = deepcopy(settings.connections)
        self._resources = {
            name: AsyncLazy(
                factory=partial(self._create, name, raw_config),
                closer=close_database_resource,
            )
            for name, raw_config in connections.items()
        }

    @property
    def default_name(self) -> str | None:
        """返回配置的默认连接名，不触发校验或资源创建。"""

        return self._default

    @property
    def connection_names(self) -> tuple[str, ...]:
        """返回声明顺序稳定的全部命名连接。"""

        return tuple(self._resources)

    def is_initialized(self, name: str | None = None) -> bool:
        """报告连接资源是否已经实际创建。"""

        resource = self._resources.get(self._resolve_name(name))
        return resource.initialized if resource is not None else False

    async def get(self, name: str | None = None) -> DatabaseResource:
        """延迟校验并获取连接资源，关闭开始后拒绝新获取。"""

        if self._closed:
            raise RuntimeError("数据库管理器已经关闭")

        resolved_name = self._resolve_name(name)
        resource = self._resources.get(resolved_name)

        if resource is None:
            raise DatabaseConfigurationError(f"数据库连接 {resolved_name!r} 未配置")

        return await resource.get()

    async def get_engine(self, name: str | None = None) -> AsyncEngine:
        """获取指定连接的异步 Engine。"""

        return (await self.get(name)).engine

    @asynccontextmanager
    async def session(self, name: str | None = None) -> AsyncIterator[AsyncSession]:
        """提供短生命周期 Session；事务提交仍由调用方显式决定。"""

        resource = await self.get(name)

        async with resource.session_factory() as session:
            yield session

    async def aclose(self) -> None:
        """封锁新获取并释放所有已初始化连接池。"""

        self._closed = True
        # 在第一次 await 前同步封锁全部资源，避免关闭期间产生新借用。
        for resource in self._resources.values():
            resource.begin_close()

        errors: list[BaseException] = []

        # 外部取消不能打断释放序列，否则部分连接池可能永久遗留。
        with CancelScope(shield=True):
            for resource in reversed(tuple(self._resources.values())):
                try:
                    await resource.aclose()
                except BaseException as error:
                    errors.append(error)

        if errors:
            raise BaseExceptionGroup("数据库资源关闭失败", errors)

    async def _create(
        self,
        name: str,
        raw_config: dict[str, object],
    ) -> DatabaseResource:
        # 原始连接配置直到首次使用才由 Provider 严格校验。
        definition = validate_database_definition(name, raw_config, self._providers)
        return await create_database_resource(name, definition)

    def _resolve_name(self, name: str | None) -> str:
        """选择显式连接名，否则要求已经配置默认连接。"""

        if name is not None:
            return name

        if self._default is None:
            raise DatabaseConfigurationError("默认数据库连接未配置")

        return self._default
