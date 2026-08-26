from app.infrastructure.cache.contracts.client import DEFAULT_EXPIRATION, NO_EXPIRATION, CacheTTL
from app.infrastructure.cache.contracts.storage import KeyValueStorage
from app.infrastructure.cache.errors import CacheOperationError
from app.infrastructure.cache.key import CacheKeyBuilder


class ManagedCacheClient:
    """为字节级 KV Storage 统一应用 key 和 TTL 规则。"""

    def __init__(
        self,
        storage: KeyValueStorage,
        key_builder: CacheKeyBuilder,
        default_ttl: int | None,
    ) -> None:
        self._storage = storage
        self._key_builder = key_builder
        self._default_ttl = default_ttl

    async def get(self, key: str) -> bytes | None:
        return await self._storage.get(self._key_builder.build(key))

    async def set(self, key: str, value: bytes, *, ttl: CacheTTL = DEFAULT_EXPIRATION) -> None:
        if not isinstance(value, bytes):
            raise TypeError("缓存值必须是 bytes")

        result = await self._storage.set(
            self._key_builder.build(key),
            value,
            self._resolve_ttl(ttl),
        )
        if not result:
            raise CacheOperationError("缓存写入未成功")

    async def delete(self, key: str) -> bool:
        return await self._storage.delete(self._key_builder.build(key))

    async def exists(self, key: str) -> bool:
        return await self._storage.exists(self._key_builder.build(key))

    def _resolve_ttl(self, ttl: CacheTTL) -> int | None:
        if ttl is DEFAULT_EXPIRATION:
            return self._default_ttl

        if ttl is NO_EXPIRATION:
            return None

        if not isinstance(ttl, int) or isinstance(ttl, bool) or ttl <= 0:
            raise ValueError("ttl 必须为正整数、DEFAULT_EXPIRATION 或 NO_EXPIRATION")

        return ttl
