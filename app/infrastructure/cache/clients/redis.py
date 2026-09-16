"""为需要 Redis 原子语义的适配器提供受控客户端。"""

from app.infrastructure.cache.clients.managed import ManagedCacheClient
from app.infrastructure.cache.contracts.storage import RedisAtomicStorage
from app.infrastructure.cache.key import CacheKeyBuilder


class ManagedRedisCacheClient(ManagedCacheClient):
    """在公共缓存能力之外显式提供 Redis String 原子操作。"""

    def __init__(
        self,
        storage: RedisAtomicStorage,
        key_builder: CacheKeyBuilder,
        default_ttl: int | None,
    ) -> None:
        """保存 Redis 聚合 Storage，同时复用公共 key 与 TTL 规则。"""

        super().__init__(storage, key_builder, default_ttl)
        self._redis_storage = storage

    async def acquire_window(self, key: str, *, limit: int, window_ms: int) -> tuple[bool, int]:
        """规范化 key 后原子消耗配额；拒绝不续期，窗口不使用默认缓存 TTL。"""

        for value, maximum in ((limit, 1_000_000), (window_ms, 86_400_000)):
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError("窗口配额或毫秒时长超出允许范围")
        return await self._redis_storage.strings.acquire_window(self._key_builder.build(key), limit, window_ms)

    async def increment(self, key: str, *, ttl: int) -> int:
        """递增规范化后的 key，并在首次创建时设置正整数 TTL。"""

        resolved_ttl = self._resolve_ttl(ttl)
        if resolved_ttl is None:
            raise ValueError("Redis 原子计数必须设置过期时间")

        return await self._redis_storage.strings.increment(
            self._key_builder.build(key),
            resolved_ttl,
        )

    async def expire(self, key: str, *, ttl: int) -> bool:
        """更新规范化后 key 的正整数 TTL，返回 key 是否存在。"""

        resolved_ttl = self._resolve_ttl(ttl)
        if resolved_ttl is None:
            raise ValueError("Redis 过期时间必须是正整数")

        return await self._redis_storage.strings.expire(
            self._key_builder.build(key),
            resolved_ttl,
        )

    async def ttl(self, key: str) -> int:
        """读取规范化后 key 的 Redis TTL 状态。"""

        return await self._redis_storage.strings.ttl(self._key_builder.build(key))
