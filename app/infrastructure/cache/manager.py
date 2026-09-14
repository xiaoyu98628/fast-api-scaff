"""管理缓存配置校验、命名连接和延迟资源生命周期。"""

from functools import partial

from pydantic import ValidationError

from app.config.cache import CacheSettings
from app.infrastructure.cache.clients.managed import ManagedCacheClient
from app.infrastructure.cache.clients.redis import ManagedRedisCacheClient
from app.infrastructure.cache.contracts.client import CacheClient
from app.infrastructure.cache.contracts.provider import CacheResourceDefinition
from app.infrastructure.cache.errors import CacheConfigurationError
from app.infrastructure.cache.key import CacheKeyBuilder
from app.infrastructure.cache.providers.registry import DEFAULT_CACHE_PROVIDERS, CacheProviderRegistry
from app.infrastructure.cache.resource import ManagedCacheResource
from app.infrastructure.cache.storages.redis.storage import RedisStorage
from app.infrastructure.resources.closing import close_lazy_resources
from app.infrastructure.resources.lazy import AsyncLazy


class CacheManager:
    """按名称管理启动校验、延迟创建的缓存客户端。"""

    def __init__(
        self,
        settings: CacheSettings,
        providers: CacheProviderRegistry = DEFAULT_CACHE_PROVIDERS,
    ) -> None:
        """校验命名连接，并为每个连接建立延迟资源句柄。"""

        self._default = settings.default
        self._closed = False
        self._namespace = settings.namespace
        self._default_ttl = settings.default_ttl
        self._providers = providers
        self._definitions = self._prepare_connections(settings)
        self._resources = {
            name: AsyncLazy(
                factory=partial(self._create, definition),
                closer=ManagedCacheResource.aclose,
            )
            for name, definition in self._definitions.items()
        }

    @property
    def default_name(self) -> str | None:
        """返回配置的默认连接名，不创建缓存资源。"""

        return self._default

    @property
    def connection_names(self) -> tuple[str, ...]:
        """返回声明顺序稳定的全部命名连接。"""

        return tuple(self._resources)

    def is_initialized(self, name: str | None = None) -> bool:
        """报告指定连接资源是否已经实际创建。"""

        resource = self._resources.get(self._resolve_name(name))
        return resource.initialized if resource is not None else False

    async def get(self, name: str | None = None) -> CacheClient:
        """延迟创建并返回统一 bytes 缓存客户端。"""

        return (await self._get_resource(name)).client

    def require_redis(self, name: str | None = None) -> str:
        """校验命名连接提供 Redis 专属能力，并返回解析后的连接名。"""

        resolved_name = self._resolve_name(name)
        definition = self._definitions.get(resolved_name)
        if definition is None:
            raise CacheConfigurationError(f"缓存连接 {resolved_name!r} 未配置")
        if definition.driver != "redis":
            raise CacheConfigurationError(f"缓存连接 {resolved_name!r} 使用 {definition.driver!r} 驱动，不支持所需的 Redis 功能")

        return resolved_name

    async def get_redis(self, name: str | None = None) -> ManagedRedisCacheClient:
        """延迟返回显式 Redis 客户端，其他驱动在创建资源前失败。"""

        resolved_name = self.require_redis(name)
        client = (await self._get_resource(resolved_name)).client
        if not isinstance(client, ManagedRedisCacheClient):
            raise CacheConfigurationError(f"缓存连接 {resolved_name!r} 没有提供 Redis 客户端")

        return client

    async def ping(self, name: str | None = None) -> bool:
        """通过指定连接的原生健康检查验证可访问性。"""

        return await (await self._get_resource(name)).ping()

    async def _get_resource(self, name: str | None = None) -> ManagedCacheResource:
        """获取生命周期受控的底层资源，关闭开始后拒绝新借用。"""

        if self._closed:
            raise RuntimeError("缓存管理器已经关闭")

        resolved_name = self._resolve_name(name)
        resource = self._resources.get(resolved_name)

        if resource is None:
            raise CacheConfigurationError(f"缓存连接 {resolved_name!r} 未配置")

        return await resource.get()

    async def aclose(self) -> None:
        """封锁新获取并释放全部已初始化缓存连接。"""

        self._closed = True
        await close_lazy_resources(self._resources.values(), error_message="缓存客户端关闭失败")

    async def _create(self, definition: CacheResourceDefinition) -> ManagedCacheResource:
        """组合驱动资源与统一 key、TTL 规则的公共客户端。"""

        resource = await definition.factory()
        key_builder = CacheKeyBuilder(self._namespace, definition.key_prefix)
        if definition.driver == "redis":
            if not isinstance(resource.storage, RedisStorage):
                raise CacheConfigurationError("Redis Provider 返回了不兼容的 Storage")
            client: CacheClient = ManagedRedisCacheClient(
                storage=resource.storage,
                key_builder=key_builder,
                default_ttl=self._default_ttl,
            )
        else:
            client = ManagedCacheClient(
                storage=resource.storage,
                key_builder=key_builder,
                default_ttl=self._default_ttl,
            )
        return ManagedCacheResource(
            connection=resource.connection,
            storage=resource.storage,
            client=client,
        )

    def _prepare_connections(self, settings: CacheSettings) -> dict[str, CacheResourceDefinition]:
        """启动时严格校验全部声明连接，但不建立外部连接。"""

        if settings.default is not None and settings.default not in settings.connections:
            raise CacheConfigurationError(f"默认缓存连接 {settings.default!r} 未配置")

        if settings.connections and not settings.namespace:
            raise CacheConfigurationError("配置缓存连接时 CACHE_NAMESPACE 不能为空")

        definitions: dict[str, CacheResourceDefinition] = {}
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
        """选择显式连接名，否则要求已经配置默认连接。"""

        if name is not None:
            return name

        if self._default is None:
            raise CacheConfigurationError("默认缓存连接未配置")

        return self._default
