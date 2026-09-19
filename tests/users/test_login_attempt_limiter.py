"""验证 Redis 登录失败限制器的计数、锁定和敏感标识处理。"""

from typing import cast
from unittest.mock import AsyncMock

import pytest

from app.contexts.user.infrastructure.security.redis_login_attempts import _CLEAR_SCRIPT, _INCREMENT_SCRIPT, RedisLoginAttemptLimiter
from app.infrastructure.cache.clients.redis import ManagedRedisCacheClient
from app.infrastructure.cache.contracts.script import RedisScriptArgument
from app.infrastructure.cache.errors import CacheOperationError


class FakeRedisCacheClient:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.expirations: dict[str, int] = {}

    async def get(self, key: str) -> bytes | None:
        count = self.counts.get(key)
        return None if count is None else str(count).encode()

    async def execute_script(self, script: str, *, keys: tuple[str, ...], args: tuple[RedisScriptArgument, ...]) -> object:
        # 测试替身按脚本身份模拟 Redis 原子结果，不解析或执行 Lua。
        key = keys[0]
        value = cast(int, args[0])
        if script == _INCREMENT_SCRIPT:
            count = self.counts.get(key, 0) + 1
            self.counts[key] = count
            if count == 1:
                self.expirations[key] = value
            return count
        assert script == _CLEAR_SCRIPT
        if self.counts.get(key, value) >= value:
            return 0
        existed = self.counts.pop(key, None) is not None
        self.expirations.pop(key, None)
        return int(existed)

    async def expire(self, key: str, *, ttl: int) -> bool:
        if key not in self.counts:
            return False
        self.expirations[key] = ttl
        return True

    async def ttl(self, key: str) -> int:
        return self.expirations.get(key, -2)


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
async def test_fifth_failure_locks_normalized_hashed_identity_and_success_preserves_lock() -> None:
    client = FakeRedisCacheClient()
    limiter = build_limiter(client)

    first = await limiter.record_failure(" Alice ")
    assert first.remaining_attempts == 4
    assert first.retry_after_seconds is None
    key = next(iter(client.counts))
    assert "alice" not in key
    assert len(key.split(":")) == 4
    assert client.expirations[key] == 300

    remaining = [await limiter.record_failure("alice") for _ in range(3)]
    assert [status.remaining_attempts for status in remaining] == [3, 2, 1]
    locked = await limiter.record_failure("ALICE")
    assert locked.remaining_attempts == 0
    assert locked.retry_after_seconds == 900
    assert client.counts[key] == 5
    assert client.expirations[key] == 900
    assert await limiter.retry_after(" alice ") == 900

    await limiter.clear("alice")
    assert await limiter.retry_after("alice") == 900
    assert client.counts[key] == 5
    assert client.expirations[key] == 900


@pytest.mark.asyncio
async def test_missing_expiration_on_locked_counter_fails_closed() -> None:
    client = FakeRedisCacheClient()
    limiter = build_limiter(client)
    key = limiter._key("alice")
    client.counts[key] = 5
    client.expirations[key] = -1

    with pytest.raises(CacheOperationError, match="缺少过期时间"):
        await limiter.retry_after("alice")


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [0, 1, 4, 5, 6])
async def test_cleanup_only_removes_below_threshold_counts(count: int) -> None:
    client = FakeRedisCacheClient()
    limiter = build_limiter(client)
    key = limiter._key("alice")
    for _ in range(count):
        await limiter.record_failure("alice")
    await limiter.clear(" ALICE ")
    if count < 5:
        assert client.counts == {}
        assert client.expirations == {}
    else:
        assert client.counts[key] == count
        assert client.expirations[key] == 900


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation,result",
    [
        ("record_failure", 0),
        ("record_failure", True),
        ("record_failure", b"1"),
        ("clear", -1),
        ("clear", 2),
        ("clear", True),
        ("clear", None),
        ("clear", b"1"),
    ],
)
async def test_login_limiter_owns_script_result_validation(operation: str, result: object) -> None:
    client = AsyncMock(spec=ManagedRedisCacheClient)
    client.execute_script.return_value = result
    limiter = RedisLoginAttemptLimiter(AsyncMock(return_value=client), 5, 300, 900)
    with pytest.raises(CacheOperationError):
        await getattr(limiter, operation)("alice")
    client.expire.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("result", [0, 1])
async def test_clear_uses_owned_script_and_does_not_modify_ttl(result: int) -> None:
    client = AsyncMock(spec=ManagedRedisCacheClient)
    client.execute_script.return_value = result
    limiter = RedisLoginAttemptLimiter(AsyncMock(return_value=client), 5, 300, 900)
    await limiter.clear(" ALICE ")
    client.execute_script.assert_awaited_once_with(_CLEAR_SCRIPT, keys=(limiter._key("alice"),), args=(5,))
    client.expire.assert_not_awaited()


@pytest.mark.asyncio
async def test_increment_passes_initial_window_to_owned_script() -> None:
    client = AsyncMock(spec=ManagedRedisCacheClient)
    client.execute_script.return_value = 1
    limiter = RedisLoginAttemptLimiter(AsyncMock(return_value=client), 5, 300, 900)
    assert (await limiter.record_failure("alice")).remaining_attempts == 4
    client.execute_script.assert_awaited_once_with(_INCREMENT_SCRIPT, keys=(limiter._key("alice"),), args=(300,))
    client.expire.assert_not_awaited()
