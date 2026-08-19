import asyncio

import pytest

from app.platform.resources.lazy import AsyncLazy


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

    initialized = await resource.get()
    await resource.aclose()

    assert closed == [initialized]
    assert resource.initialized is False
