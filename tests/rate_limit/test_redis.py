"""验证配额适配器的 key 隔离、等待时间、异常及取消边界。"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.infrastructure.cache.errors import CacheConnectionError, CacheOperationError
from app.infrastructure.rate_limit.contracts import RateLimitUnavailableError
from app.infrastructure.rate_limit.redis import RedisFixedWindowLimiter


@pytest.mark.asyncio
@pytest.mark.parametrize("ttl,expected", [(0, 1), (1, 1), (1000, 1), (1001, 2), (60_000, 60)])
async def test_retry_after_rounds_up(ttl: int, expected: int) -> None:
    client = AsyncMock()
    client.acquire_window.return_value = (False, ttl)
    limiter = RedisFixedWindowLimiter(AsyncMock(return_value=client), 1000, 60)
    decision = await limiter.acquire("ip:192.0.2.1")
    assert not decision.allowed
    assert decision.retry_after_seconds == expected


@pytest.mark.asyncio
async def test_identity_and_policy_isolation_without_raw_ip() -> None:
    client = AsyncMock()
    client.acquire_window.return_value = (True, 0)
    factory = AsyncMock(return_value=client)
    limiter = RedisFixedWindowLimiter(factory, 1000, 60)
    assert (await limiter.acquire("ip:192.0.2.1")).allowed
    await limiter.acquire("ip:192.0.2.1")
    await limiter.acquire("ip:192.0.2.2")
    await RedisFixedWindowLimiter(factory, 2000, 60).acquire("ip:192.0.2.1")
    await RedisFixedWindowLimiter(factory, 1000, 120).acquire("ip:192.0.2.1")
    keys = [call.args[0] for call in client.acquire_window.await_args_list]
    assert keys[0] == keys[1]
    assert len(set(keys)) == 4
    assert all("192.0.2" not in key for key in keys)
    assert client.acquire_window.await_args_list[0].kwargs == {"limit": 1000, "window_ms": 60_000}


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [CacheOperationError("failed"), CacheConnectionError("failed")])
@pytest.mark.parametrize("during_factory", [False, True])
async def test_storage_errors_are_translated(error: Exception, during_factory: bool) -> None:
    client = AsyncMock()
    client.acquire_window.side_effect = error
    factory = AsyncMock(side_effect=error) if during_factory else AsyncMock(return_value=client)
    with pytest.raises(RateLimitUnavailableError) as captured:
        await RedisFixedWindowLimiter(factory, 1000, 60).acquire("ip:192.0.2.1")
    assert captured.value.__cause__ is error


@pytest.mark.asyncio
async def test_cancellation_is_not_converted_to_dependency_failure() -> None:
    factory = AsyncMock(side_effect=asyncio.CancelledError)
    with pytest.raises(asyncio.CancelledError):
        await RedisFixedWindowLimiter(factory, 1000, 60).acquire("ip:192.0.2.1")
