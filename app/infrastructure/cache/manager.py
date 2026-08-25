from functools import partial

from pydantic import ValidationError

from app.config.cache import CacheSettings
from app.infrastructure.cache.clients.managed import ManagedCacheClient
from app.infrastructure.cache.contracts.client import CacheClient
from app.infrastructure.cache.contracts.provider import CacheBackendDefinition
from app.infrastructure.cache.errors import CacheConfigurationError
from app.infrastructure.cache.key import CacheKeyBuilder
from app.infrastructure.cache.providers.registry import DEFAULT_CACHE_PROVIDERS, CacheProviderRegistry
from app.infrastructure.resources.lazy import AsyncLazy


class CacheManager:
    """按名称管理启动校验、延迟创建的缓存客户端。"""

    def __init__(
        self,
        settings: CacheSettings,
        providers: CacheProviderRegistry = DEFAULT_CACHE_PROVIDERS,
    ) -> None:
        self._default = settings.default
        self._namespace = settings.namespace
        self._default_ttl = settings.default_ttl
        self._providers = providers
        definitions = self._prepare_connections(settings)
        self._clients = {
            name: AsyncLazy(
                factory=partial(self._create, definition),
                closer=ManagedCacheClient.aclose,
            )
            for name, definition in definitions.items()
        }

    @property
    def default_name(self) -> str | None:
        return self._default

    @property
    def connection_names(self) -> tuple[str, ...]:
        return tuple(self._clients)

    def is_initialized(self, name: str | None = None) -> bool:
        client = self._clients.get(self._resolve_name(name))
        return client.initialized if client is not None else False

    async def get(self, name: str | None = None) -> CacheClient:
        return await self._get_managed(name)

    async def ping(self, name: str | None = None) -> bool:
        return await (await self._get_managed(name)).ping()

    async def _get_managed(self, name: str | None = None) -> ManagedCacheClient:
        resolved_name = self._resolve_name(name)
        client = self._clients.get(resolved_name)

        if client is None:
            raise CacheConfigurationError(f"缓存连接 {resolved_name!r} 未配置")

        return await client.get()

    async def aclose(self) -> None:
        errors: list[Exception] = []

        for client in reversed(tuple(self._clients.values())):
            try:
                await client.aclose()
            except Exception as error:
                errors.append(error)

        if errors:
            raise ExceptionGroup("缓存客户端关闭失败", errors)

    async def _create(self, definition: CacheBackendDefinition) -> ManagedCacheClient:
        backend = await definition.factory()
        return ManagedCacheClient(
            backend=backend,
            key_builder=CacheKeyBuilder(self._namespace, definition.key_prefix),
            default_ttl=self._default_ttl,
        )

    def _prepare_connections(self, settings: CacheSettings) -> dict[str, CacheBackendDefinition]:
        if settings.default is not None and settings.default not in settings.connections:
            raise CacheConfigurationError(f"默认缓存连接 {settings.default!r} 未配置")

        if settings.connections and not settings.namespace:
            raise CacheConfigurationError("配置缓存连接时 CACHE_NAMESPACE 不能为空")

        definitions: dict[str, CacheBackendDefinition] = {}
        for name, raw_config in settings.connections.items():
            if not name or name.isspace():
                raise CacheConfigurationError("缓存连接名不能为空")

            try:
                definition = self._providers.prepare(raw_config)
                CacheKeyBuilder(settings.namespace, definition.key_prefix)
            except (ValidationError, CacheConfigurationError) as error:
                raise CacheConfigurationError(f"缓存连接 {name!r} 配置不合法") from error

            definitions[name] = definition

        return definitions

    def _resolve_name(self, name: str | None) -> str:
        if name is not None:
            return name

        if self._default is None:
            raise CacheConfigurationError("默认缓存连接未配置")

        return self._default
