from functools import partial

from pydantic import TypeAdapter, ValidationError

from app.config.cache import CacheConnectionSettings, CacheSettings
from app.infrastructure.cache.client import CacheClient
from app.infrastructure.cache.errors import CacheConfigurationError
from app.infrastructure.cache.factory import close_cache_client, create_cache_client
from app.infrastructure.resources.lazy import AsyncLazy

CACHE_CONNECTION_ADAPTER = TypeAdapter(CacheConnectionSettings)


class CacheManager:
    """按名称管理延迟校验、延迟创建的缓存客户端。"""

    def __init__(self, settings: CacheSettings) -> None:
        self._default = settings.default
        self._key_prefix = settings.key_prefix
        self._clients = {
            name: AsyncLazy(
                factory=partial(self._create, name, raw_config),
                closer=close_cache_client,
            )
            for name, raw_config in settings.connections.items()
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

    async def _create(self, name: str, raw_config: dict[str, object]) -> CacheClient:
        try:
            settings = CACHE_CONNECTION_ADAPTER.validate_python(raw_config)
        except ValidationError:
            raise CacheConfigurationError(f"缓存连接 {name!r} 配置不合法") from None

        return await create_cache_client(settings, default_key_prefix=self._key_prefix)

    def _resolve_name(self, name: str | None) -> str:
        if name is not None:
            return name

        if self._default is None:
            raise CacheConfigurationError("默认缓存连接未配置")

        return self._default
