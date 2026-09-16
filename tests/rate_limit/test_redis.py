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
    client.execute_script.return_value = (0, ttl)
    limiter = RedisFixedWindowLimiter(AsyncMock(return_value=client), 1000, 60)
    decision = await limiter.acquire("ip:192.0.2.1")
    assert not decision.allowed
    assert decision.retry_after_seconds == expected


@pytest.mark.asyncio
async def test_identity_and_policy_isolation_without_raw_ip() -> None:
    client = AsyncMock()
    client.execute_script.return_value = (1, 0)
    factory = AsyncMock(return_value=client)
    limiter = RedisFixedWindowLimiter(factory, 1000, 60)
    assert (await limiter.acquire("ip:192.0.2.1")).allowed
    await limiter.acquire("ip:192.0.2.1")
    await limiter.acquire("ip:192.0.2.2")
    await RedisFixedWindowLimiter(factory, 2000, 60).acquire("ip:192.0.2.1")
    await RedisFixedWindowLimiter(factory, 1000, 120).acquire("ip:192.0.2.1")
    keys = [call.kwargs["keys"][0] for call in client.execute_script.await_args_list]
    assert keys[0] == keys[1]
    assert len(set(keys)) == 4
    assert all("192.0.2" not in key for key in keys)
    assert client.execute_script.await_args_list[0].kwargs == {"keys": (keys[0],), "args": (1000, 60_000)}


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [CacheOperationError("failed"), CacheConnectionError("failed")])
@pytest.mark.parametrize("during_factory", [False, True])
async def test_storage_errors_are_translated(error: Exception, during_factory: bool) -> None:
    client = AsyncMock()
    client.execute_script.side_effect = error
    factory = AsyncMock(side_effect=error) if during_factory else AsyncMock(return_value=client)
    with pytest.raises(RateLimitUnavailableError) as captured:
        await RedisFixedWindowLimiter(factory, 1000, 60).acquire("ip:192.0.2.1")
    assert captured.value.__cause__ is error


@pytest.mark.asyncio
async def test_cancellation_is_not_converted_to_dependency_failure() -> None:
    factory = AsyncMock(side_effect=asyncio.CancelledError)
    with pytest.raises(asyncio.CancelledError):
        await RedisFixedWindowLimiter(factory, 1000, 60).acquire("ip:192.0.2.1")


@pytest.mark.asyncio
@pytest.mark.parametrize("result", [None, [], [1], [1, 1], [0, -1], [0, 60_001], [True, 0], [0, False], [2, 0], ["1", 0]])
async def test_limiter_owns_script_result_validation(result: object) -> None:
    client = AsyncMock()
    client.execute_script.return_value = result
    with pytest.raises(RateLimitUnavailableError) as captured:
        await RedisFixedWindowLimiter(AsyncMock(return_value=client), 1000, 60).acquire("ip:192.0.2.1")
    assert isinstance(captured.value.__cause__, CacheOperationError)


@pytest.mark.parametrize("limit,window", [(0, 1), (True, 1), (1_000_001, 1), (1, 0), (1, 86_401)])
def test_limiter_owns_policy_validation(limit: int, window: int) -> None:
    with pytest.raises(ValueError):
        RedisFixedWindowLimiter(AsyncMock(), limit, window)
