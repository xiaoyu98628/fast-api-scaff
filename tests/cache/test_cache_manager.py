import asyncio

import pytest

from app.config.cache import CacheSettings
from app.infrastructure.cache.clients.managed import ManagedCacheClient
from app.infrastructure.cache.errors import CacheConfigurationError
from app.infrastructure.cache.manager import CacheManager


def test_invalid_connection_is_reported_when_manager_is_built() -> None:
    settings = CacheSettings(
        default="broken",
        namespace="test",
        connections={"broken": {"driver": "redis"}},
        _env_file=None,
    )

    with pytest.raises(CacheConfigurationError, match="broken"):
        CacheManager(settings)


def test_configured_connection_requires_namespace() -> None:
    settings = CacheSettings(
        default="main",
        connections={"main": {"driver": "memory"}},
        _env_file=None,
    )

    with pytest.raises(CacheConfigurationError, match="CACHE_NAMESPACE"):
        CacheManager(settings)


def test_default_connection_must_exist() -> None:
    settings = CacheSettings(default="missing", namespace="test", _env_file=None)

    with pytest.raises(CacheConfigurationError, match="missing"):
        CacheManager(settings)


@pytest.mark.asyncio
async def test_network_client_is_created_without_connecting() -> None:
    settings = CacheSettings(
        default="main",
        namespace="test",
        connections={"main": {"driver": "redis", "host": "127.0.0.1"}},
        _env_file=None,
    )
    manager = CacheManager(settings)

    client = await manager.get()

    assert isinstance(client, ManagedCacheClient)
    assert manager.is_initialized() is True
    await manager.aclose()


@pytest.mark.asyncio
async def test_default_and_named_connections_are_independent() -> None:
    settings = CacheSettings(
        default="session",
        namespace="test",
        connections={
            "session": {"driver": "memory", "key_prefix": "session"},
            "page": {"driver": "memory", "key_prefix": "page"},
        },
        _env_file=None,
    )
    manager = CacheManager(settings)

    page = await manager.get("page")
    await page.set("home", b"page")

    assert manager.is_initialized("page") is True
    assert manager.is_initialized("session") is False

    session = await manager.get()
    assert session is not page
    assert await session.get("home") is None

    await manager.aclose()
    assert manager.is_initialized("page") is False
    assert manager.is_initialized("session") is False


@pytest.mark.asyncio
async def test_concurrent_get_creates_named_client_once() -> None:
    settings = CacheSettings(
        default="main",
        namespace="test",
        connections={"main": {"driver": "memory"}},
        _env_file=None,
    )
    manager = CacheManager(settings)

    first, second = await asyncio.gather(manager.get(), manager.get())

    assert first is second
    assert await manager.ping() is True
    await manager.aclose()


@pytest.mark.asyncio
async def test_missing_default_is_reported_when_implicit_connection_is_requested() -> None:
    manager = CacheManager(CacheSettings(_env_file=None))

    with pytest.raises(CacheConfigurationError, match="默认缓存连接"):
        await manager.get()


@pytest.mark.parametrize("initialize_first", [False, True])
@pytest.mark.asyncio
async def test_manager_rejects_gets_as_soon_as_close_starts(monkeypatch: pytest.MonkeyPatch, initialize_first: bool) -> None:
    manager = CacheManager(CacheSettings(_env_file=None, namespace="test", connections={name: {"driver": "memory"} for name in ("first", "second")}))
    if initialize_first:
        await manager.get("first")
    await manager.get("second")
    closing_started = asyncio.Event()
    release = asyncio.Event()
    second_resource = manager._resources["second"]
    original_close = second_resource._closer

    async def delayed_close(resource):
        closing_started.set()
        await release.wait()
        await original_close(resource)

    monkeypatch.setattr(second_resource, "_closer", delayed_close)
    closing = asyncio.create_task(manager.aclose())
    try:
        await closing_started.wait()
        with pytest.raises(RuntimeError, match="已经关闭"):
            await manager.get("first")
        with pytest.raises(RuntimeError, match="已经关闭"):
            await manager.get("second")
        assert manager.is_initialized("first") is initialize_first
    finally:
        release.set()
        await closing
    await manager.aclose()
    assert not manager.is_initialized("first")
    assert not manager.is_initialized("second")


@pytest.mark.asyncio
async def test_failed_close_keeps_manager_closed_and_cleans_other_resources(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = CacheManager(CacheSettings(_env_file=None, namespace="test", connections={name: {"driver": "memory"} for name in ("first", "second")}))
    await manager.get("first")
    await manager.get("second")
    second_resource = manager._resources["second"]
    original_close = second_resource._closer
    original_error = RuntimeError("close failed")

    async def failing_close(_resource):
        raise original_error

    monkeypatch.setattr(second_resource, "_closer", failing_close)
    try:
        with pytest.raises(ExceptionGroup) as captured:
            await manager.aclose()
        assert captured.value.exceptions == (original_error,)
        assert not manager.is_initialized("first")
        for name in ("first", "second"):
            with pytest.raises(RuntimeError, match="已经关闭"):
                await manager.get(name)
    finally:
        monkeypatch.setattr(second_resource, "_closer", original_close)
        await manager.aclose()
