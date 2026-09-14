"""验证异步资源的并发懒加载和关闭竞态。"""

import asyncio

import pytest
from anyio import CancelScope, sleep

from app.infrastructure.resources.closing import close_lazy_resources
from app.infrastructure.resources.lazy import AsyncLazy


@pytest.mark.asyncio
async def test_concurrent_get_creates_resource_once() -> None:
    create_count = 0

    async def create() -> object:
        nonlocal create_count
        create_count += 1
        await asyncio.sleep(0)
        return object()

    async def close(_resource: object) -> None:
        return None

    resource = AsyncLazy(factory=create, closer=close)

    first, second = await asyncio.gather(resource.get(), resource.get())

    assert first is second
    assert create_count == 1
    assert resource.initialized is True


@pytest.mark.asyncio
async def test_close_only_closes_initialized_resource() -> None:
    closed: list[object] = []

    async def create() -> object:
        return object()

    async def close(resource: object) -> None:
        closed.append(resource)

    resource = AsyncLazy(factory=create, closer=close)

    await resource.aclose()
    assert closed == []

    initialized_resource = AsyncLazy(factory=create, closer=close)
    initialized = await initialized_resource.get()
    await initialized_resource.aclose()

    assert closed == [initialized]
    assert initialized_resource.initialized is False


@pytest.mark.asyncio
async def test_get_waiting_for_close_is_rejected_and_resource_cannot_reopen() -> None:
    close_started = asyncio.Event()
    allow_close = asyncio.Event()

    async def create() -> object:
        return object()

    async def close(_resource: object) -> None:
        close_started.set()
        await allow_close.wait()

    resource = AsyncLazy(factory=create, closer=close)
    await resource.get()
    close_task = asyncio.create_task(resource.aclose())
    await close_started.wait()
    get_task = asyncio.create_task(resource.get())
    await asyncio.sleep(0)

    assert get_task.done() is True

    allow_close.set()
    await close_task

    with pytest.raises(RuntimeError, match="已经关闭"):
        await get_task

    with pytest.raises(RuntimeError, match="已经关闭"):
        await resource.get()


@pytest.mark.asyncio
async def test_close_during_initialization_rejects_active_and_queued_gets() -> None:
    initializing = asyncio.Event()
    release = asyncio.Event()
    value = object()
    closed: list[object] = []
    create_count = 0

    async def create() -> object:
        nonlocal create_count
        create_count += 1
        initializing.set()
        await release.wait()
        return value

    async def close(resource: object) -> None:
        closed.append(resource)

    resource = AsyncLazy(create, close)
    first = asyncio.create_task(resource.get())
    await initializing.wait()
    queued = asyncio.create_task(resource.get())
    await asyncio.sleep(0)
    closing = asyncio.create_task(resource.aclose())
    await asyncio.sleep(0)
    release.set()
    results = await asyncio.gather(first, queued, closing, return_exceptions=True)
    assert isinstance(results[0], RuntimeError)
    assert isinstance(results[1], RuntimeError)
    assert results[2] is None
    assert create_count == 1
    assert closed == [value]
    assert not resource.initialized
    await resource.aclose()
    assert closed == [value]


@pytest.mark.asyncio
async def test_group_close_seals_all_handles_aggregates_failures_and_retries() -> None:
    events: list[int] = []
    failures = {1: RuntimeError("first failure"), 2: asyncio.CancelledError("second failure")}

    async def create() -> object:
        return object()

    def make_resource(index: int) -> AsyncLazy[object]:
        async def close(_value: object) -> None:
            # 第一个关闭回调也不能重新获取组内尚未释放的资源。
            for resource in resources:
                with pytest.raises(RuntimeError, match="已经关闭"):
                    await resource.get()
            events.append(index)
            if index in failures:
                raise failures[index]

        return AsyncLazy(create, close)

    resources = [make_resource(index) for index in range(4)]
    for resource in resources[:3]:
        await resource.get()
    with pytest.raises(BaseExceptionGroup) as captured:
        await close_lazy_resources(iter(resources), error_message="group failed")
    assert captured.value.message == "group failed"
    assert captured.value.exceptions == (failures[2], failures[1])
    assert events == [2, 1, 0]
    assert [resource.initialized for resource in resources] == [False, True, True, False]

    failures.clear()
    await close_lazy_resources(resources, error_message="group failed")
    await close_lazy_resources(resources, error_message="group failed")
    assert events == [2, 1, 0, 2, 1]
    assert not any(resource.initialized for resource in resources)


@pytest.mark.asyncio
async def test_group_close_shields_outer_anyio_cancellation() -> None:
    closed: list[object] = []

    async def create() -> object:
        return object()

    async def close(value: object) -> None:
        await sleep(0)
        closed.append(value)

    resources = [AsyncLazy(create, close) for _ in range(2)]
    values = [await resource.get() for resource in resources]
    with CancelScope() as scope:
        scope.cancel()
        await close_lazy_resources(resources, error_message="group failed")
    assert closed == list(reversed(values))
