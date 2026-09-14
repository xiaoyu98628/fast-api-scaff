"""使用 Redis 原子计数实现按用户名维度的登录失败限制。"""

import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.contexts.user.application.login_attempts import LoginFailureStatus
from app.infrastructure.cache.clients.redis import ManagedRedisCacheClient
from app.infrastructure.cache.errors import CacheOperationError

type RedisCacheClientFactory = Callable[[], Awaitable[ManagedRedisCacheClient]]


@dataclass(frozen=True, slots=True)
class RedisLoginAttemptLimiter:
    """在固定窗口内累计失败，并在达到阈值后延长锁定 TTL。"""

    client_factory: RedisCacheClientFactory
    max_failures: int
    failure_window_seconds: int
    lock_seconds: int

    def __post_init__(self) -> None:
        """防止直接构造适配器时绕过正整数约束。"""

        values = (self.max_failures, self.failure_window_seconds, self.lock_seconds)
        if any(not isinstance(value, int) or isinstance(value, bool) or value <= 0 for value in values):
            raise ValueError("登录限制参数必须为正整数")

    async def retry_after(self, identity: str) -> int | None:
        """读取失败计数，仅在达到阈值且 key 尚未过期时返回 TTL。"""

        client = await self.client_factory()
        key = self._key(identity)
        raw_count = await client.get(key)
        if raw_count is None:
            return None

        if self._decode_count(raw_count) < self.max_failures:
            return None

        ttl = await client.ttl(key)
        if ttl == -2:
            return None
        if ttl == -1:
            raise CacheOperationError("登录失败计数缺少过期时间")

        # Redis 可以在不足一秒时返回 0；HTTP Retry-After 仍需正整数。
        return max(1, ttl)

    async def record_failure(self, identity: str) -> LoginFailureStatus:
        """原子累计一次失败，并返回剩余次数或锁定有效期。"""

        client = await self.client_factory()
        key = self._key(identity)
        count = await client.increment(key, ttl=self.failure_window_seconds)
        if count < self.max_failures:
            return LoginFailureStatus(remaining_attempts=self.max_failures - count)

        # 达到阈值后延长同一个计数 key；锁定判断始终以计数和 TTL 为准。
        if not await client.expire(key, ttl=self.lock_seconds):
            raise CacheOperationError("登录失败计数过期时间更新未生效")

        return LoginFailureStatus(remaining_attempts=0, retry_after_seconds=self.lock_seconds)

    async def clear(self, identity: str) -> None:
        """在登录成功后删除该标识的失败计数。"""

        client = await self.client_factory()
        await client.delete(self._key(identity))

    @staticmethod
    def _key(identity: str) -> str:
        """只把规范化标识摘要写入缓存 key，避免泄露原始用户名。"""

        normalized = identity.strip().lower()
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        return f"auth:login:{digest}:failures"

    @staticmethod
    def _decode_count(value: bytes) -> int:
        """严格解析 Redis INCR 产生的正十进制字节串。"""

        if not value.isdigit():
            raise CacheOperationError("登录失败计数不是有效的正整数")

        count = int(value)
        if count <= 0:
            raise CacheOperationError("登录失败计数不是有效的正整数")

        return count
