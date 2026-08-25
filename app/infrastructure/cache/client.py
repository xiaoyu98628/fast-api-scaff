from enum import Enum, auto
from typing import Protocol

from app.infrastructure.cache.backends.base import CacheBackend
from app.infrastructure.cache.errors import CacheOperationError
from app.infrastructure.cache.key import CacheKeyBuilder


class CacheExpiration(Enum):
    DEFAULT = auto()
    NEVER = auto()


DEFAULT_EXPIRATION = CacheExpiration.DEFAULT
NO_EXPIRATION = CacheExpiration.NEVER

type CacheTTL = int | CacheExpiration


class CacheClient(Protocol):
    """业务代码可依赖的最小异步缓存能力。"""

    async def get(self, key: str) -> bytes | None: ...

    async def set(self, key: str, value: bytes, *, ttl: CacheTTL = DEFAULT_EXPIRATION) -> None: ...

    async def delete(self, key: str) -> bool: ...

    async def exists(self, key: str) -> bool: ...


class ManagedCacheClient:
    """为缓存后端统一应用 key、TTL 和生命周期规则。"""

    def __init__(
        self,
        backend: CacheBackend,
        key_builder: CacheKeyBuilder,
        default_ttl: int | None,
    ) -> None:
        self._backend = backend
        self._key_builder = key_builder
        self._default_ttl = default_ttl

    async def get(self, key: str) -> bytes | None:
        return await self._backend.get(self._key_builder.build(key))

    async def set(self, key: str, value: bytes, *, ttl: CacheTTL = DEFAULT_EXPIRATION) -> None:
        if not isinstance(value, bytes):
            raise TypeError("缓存值必须是 bytes")

        result = await self._backend.set(
            self._key_builder.build(key),
            value,
            self._resolve_ttl(ttl),
        )
        if not result:
            raise CacheOperationError("缓存写入未成功")

    async def delete(self, key: str) -> bool:
        return await self._backend.delete(self._key_builder.build(key))

    async def exists(self, key: str) -> bool:
        return await self._backend.exists(self._key_builder.build(key))

    async def ping(self) -> bool:
        return await self._backend.ping()

    async def aclose(self) -> None:
        await self._backend.aclose()

    def _resolve_ttl(self, ttl: CacheTTL) -> int | None:
        if ttl is DEFAULT_EXPIRATION:
            return self._default_ttl

        if ttl is NO_EXPIRATION:
            return None

        if isinstance(ttl, bool) or ttl <= 0:
            raise ValueError("ttl 必须为正整数、DEFAULT_EXPIRATION 或 NO_EXPIRATION")

        return ttl
