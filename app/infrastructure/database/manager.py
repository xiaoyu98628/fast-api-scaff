from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import partial

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
        self._default = settings.default
        self._providers = providers
        self._resources = {
            name: AsyncLazy(
                factory=partial(self._create, name, raw_config),
                closer=close_database_resource,
            )
            for name, raw_config in settings.connections.items()
        }

    @property
    def default_name(self) -> str | None:
        return self._default

    @property
    def connection_names(self) -> tuple[str, ...]:
        return tuple(self._resources)

    def is_initialized(self, name: str | None = None) -> bool:
        resource = self._resources.get(self._resolve_name(name))
        return resource.initialized if resource is not None else False

    async def get(self, name: str | None = None) -> DatabaseResource:
        resolved_name = self._resolve_name(name)
        resource = self._resources.get(resolved_name)

        if resource is None:
            raise DatabaseConfigurationError(f"数据库连接 {resolved_name!r} 未配置")

        return await resource.get()

    async def get_engine(self, name: str | None = None) -> AsyncEngine:
        return (await self.get(name)).engine

    @asynccontextmanager
    async def session(self, name: str | None = None) -> AsyncIterator[AsyncSession]:
        resource = await self.get(name)

        async with resource.session_factory() as session:
            yield session

    async def aclose(self) -> None:
        errors: list[Exception] = []

        for resource in reversed(tuple(self._resources.values())):
            try:
                await resource.aclose()
            except Exception as error:
                errors.append(error)

        if errors:
            raise ExceptionGroup("数据库资源关闭失败", errors)

    async def _create(
        self,
        name: str,
        raw_config: dict[str, object],
    ) -> DatabaseResource:
        definition = validate_database_definition(name, raw_config, self._providers)
        return await create_database_resource(name, definition)

    def _resolve_name(self, name: str | None) -> str:
        if name is not None:
            return name

        if self._default is None:
            raise DatabaseConfigurationError("默认数据库连接未配置")

        return self._default
