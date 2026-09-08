"""在底层字节存储之上统一 key、TTL 和写入失败语义。"""

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
        """规范化 key 后读取原始字节。"""

        return await self._storage.get(self._key_builder.build(key))

    async def set(self, key: str, value: bytes, *, ttl: CacheTTL = DEFAULT_EXPIRATION) -> None:
        """写入 bytes，并把公共 TTL 哨兵转换为驱动存储语义。"""

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
        """删除规范化 key，返回删除前是否存在。"""

        return await self._storage.delete(self._key_builder.build(key))

    async def exists(self, key: str) -> bool:
        """检查规范化 key 当前是否有效。"""

        return await self._storage.exists(self._key_builder.build(key))

    def _resolve_ttl(self, ttl: CacheTTL) -> int | None:
        """区分默认过期、永不过期和显式正整数秒数。"""

        if ttl is DEFAULT_EXPIRATION:
            return self._default_ttl

        if ttl is NO_EXPIRATION:
            return None

        if not isinstance(ttl, int) or isinstance(ttl, bool) or ttl <= 0:
            raise ValueError("ttl 必须为正整数、DEFAULT_EXPIRATION 或 NO_EXPIRATION")

        return ttl
