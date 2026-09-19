"""通过受控 Redis 客户端实现共享固定窗口配额。"""

import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from app.infrastructure.cache.clients.redis import ManagedRedisCacheClient
from app.infrastructure.cache.errors import CacheConnectionError, CacheOperationError
from app.infrastructure.rate_limit.contracts import RateLimitDecision, RateLimitUnavailableError

type RedisClientFactory = Callable[[], Awaitable[ManagedRedisCacheClient]]


# 固定窗口策略随限流组件发布，公共缓存层只负责执行。
_WINDOW_SCRIPT = (Path(__file__).parent / "scripts" / "acquire_window.lua").read_text(encoding="utf-8")


@dataclass(frozen=True, slots=True)
class RedisFixedWindowLimiter:
    """复用缓存连接；配额窗口由首次成功准入创建。"""

    client_factory: RedisClientFactory
    max_requests: int
    window_seconds: int

    def __post_init__(self) -> None:
        """避免直接构造组件时绕过配置约束。"""

        for value, maximum in ((self.max_requests, 1_000_000), (self.window_seconds, 86_400)):
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError("限流配额或窗口超出允许范围")

    async def acquire(self, identity: str) -> RateLimitDecision:
        """原子判断并消耗配额，不接管缓存资源生命周期。"""

        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        # 配置变化后使用独立窗口；不把原始客户端标识写入 key。
        key = f"rate-limit:http:ip:{self.max_requests}:{self.window_seconds}:{digest}"
        try:
            client = await self.client_factory()
            result = await client.execute_script(_WINDOW_SCRIPT, keys=(key,), args=(self.max_requests, self.window_seconds * 1000))
            allowed, retry_after_ms = self._parse_result(result)
        except (CacheConnectionError, CacheOperationError) as error:
            raise RateLimitUnavailableError("限流存储不可用") from error

        return RateLimitDecision(
            allowed=allowed,
            retry_after_seconds=0 if allowed else max(1, (retry_after_ms + 999) // 1000),
        )

    def _parse_result(self, result: object) -> tuple[bool, int]:
        """在限流组件边界校验准入与剩余窗口，异常结果沿用存储不可用语义。"""

        if not isinstance(result, (list, tuple)) or len(result) != 2:
            raise CacheOperationError("Redis 返回了无效的配额结果")
        allowed, ttl = result
        if type(allowed) is not int or allowed not in (0, 1) or type(ttl) is not int or not 0 <= ttl <= self.window_seconds * 1000:
            raise CacheOperationError("Redis 返回了无效的配额状态")
        if allowed == 1 and ttl != 0:
            raise CacheOperationError("Redis 返回了无效的配额状态")
        return bool(allowed), ttl
