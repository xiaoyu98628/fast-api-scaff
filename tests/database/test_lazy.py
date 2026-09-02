import asyncio

import pytest

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

    assert get_task.done() is False

    allow_close.set()
    await close_task

    with pytest.raises(RuntimeError, match="已经关闭"):
        await get_task

    with pytest.raises(RuntimeError, match="已经关闭"):
        await resource.get()
