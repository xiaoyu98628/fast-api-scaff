"""验证 Redis 登录失败限制器的计数、锁定和敏感标识处理。"""

from typing import cast

import pytest

from app.contexts.user.infrastructure.security.redis_login_attempts import RedisLoginAttemptLimiter
from app.infrastructure.cache.clients.redis import ManagedRedisCacheClient
from app.infrastructure.cache.errors import CacheOperationError


class FakeRedisCacheClient:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.expirations: dict[str, int] = {}

    async def get(self, key: str) -> bytes | None:
        count = self.counts.get(key)
        return None if count is None else str(count).encode()

    async def increment(self, key: str, *, ttl: int) -> int:
        count = self.counts.get(key, 0) + 1
        self.counts[key] = count
        if count == 1:
            self.expirations[key] = ttl
        return count

    async def expire(self, key: str, *, ttl: int) -> bool:
        if key not in self.counts:
            return False
        self.expirations[key] = ttl
        return True

    async def ttl(self, key: str) -> int:
        return self.expirations.get(key, -2)

    async def delete(self, key: str) -> bool:
        existed = self.counts.pop(key, None) is not None
        self.expirations.pop(key, None)
        return existed


def build_limiter(client: FakeRedisCacheClient) -> RedisLoginAttemptLimiter:
    async def provide_client() -> ManagedRedisCacheClient:
        return cast(ManagedRedisCacheClient, client)

    return RedisLoginAttemptLimiter(
        client_factory=provide_client,
        max_failures=5,
        failure_window_seconds=300,
        lock_seconds=900,
    )


@pytest.mark.asyncio
async def test_fifth_failure_locks_normalized_hashed_identity_and_success_clears() -> None:
    client = FakeRedisCacheClient()
    limiter = build_limiter(client)

    assert await limiter.record_failure(" Alice ") is None
    key = next(iter(client.counts))
    assert "alice" not in key
    assert len(key.split(":")) == 4
    assert client.expirations[key] == 300

    for _ in range(3):
        assert await limiter.record_failure("alice") is None
    assert await limiter.record_failure("ALICE") == 900
    assert client.counts[key] == 5
    assert client.expirations[key] == 900
    assert await limiter.retry_after(" alice ") == 900

    await limiter.clear("alice")
    assert await limiter.retry_after("alice") is None
    assert client.counts == {}


@pytest.mark.asyncio
async def test_missing_expiration_on_locked_counter_fails_closed() -> None:
    client = FakeRedisCacheClient()
    limiter = build_limiter(client)
    key = limiter._key("alice")
    client.counts[key] = 5
    client.expirations[key] = -1

    with pytest.raises(CacheOperationError, match="缺少过期时间"):
        await limiter.retry_after("alice")
