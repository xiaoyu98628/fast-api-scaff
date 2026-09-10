"""验证向量存储管理器的命名资源、并发和关闭语义。"""

import asyncio

import pytest

from app.config.vector import VectorSettings
from app.infrastructure.vector.errors import VectorConfigurationError
from app.infrastructure.vector.manager import VectorStoreManager
from app.infrastructure.vector.providers.registry import DEFAULT_VECTOR_PROVIDERS, VectorProviderRegistry
from tests.vector.fakes import FakeVectorProvider


def _settings(*names: str, default: str | None = None) -> VectorSettings:
    return VectorSettings(
        default=default,
        connections={name: {"driver": "fake"} for name in names},
        _env_file=None,
    )


def test_default_connection_must_exist() -> None:
    with pytest.raises(VectorConfigurationError, match="missing"):
        VectorStoreManager(VectorSettings(default="missing", _env_file=None))


def test_invalid_connection_is_reported_when_manager_is_built() -> None:
    settings = VectorSettings(connections={"broken": {"driver": "milvus", "mode": "local"}}, _env_file=None)

    with pytest.raises(VectorConfigurationError, match="broken"):
        VectorStoreManager(settings)


@pytest.mark.asyncio
async def test_default_and_named_connections_are_independent_and_lazy() -> None:
    provider = FakeVectorProvider()
    manager = VectorStoreManager(
        _settings("knowledge", "catalog", default="knowledge"),
        providers=VectorProviderRegistry((provider,)),
    )

    catalog = await manager.get("catalog")

    assert manager.connection_names == ("knowledge", "catalog")
    assert manager.is_initialized("catalog") is True
    assert manager.is_initialized("knowledge") is False
    assert await manager.get() is not catalog
    assert len(provider.clients) == 2

    await manager.aclose()
    assert all(client.closed for client in provider.clients)


@pytest.mark.asyncio
async def test_concurrent_get_creates_named_client_once() -> None:
    provider = FakeVectorProvider()
    manager = VectorStoreManager(
        _settings("knowledge", default="knowledge"),
        providers=VectorProviderRegistry((provider,)),
    )

    first, second = await asyncio.gather(manager.get(), manager.get())

    assert first is second
    assert len(provider.clients) == 1
    assert await manager.ping() is True
    await manager.aclose()


@pytest.mark.asyncio
async def test_missing_implicit_connection_and_closed_manager_are_rejected() -> None:
    empty = VectorStoreManager(VectorSettings(_env_file=None))
    with pytest.raises(VectorConfigurationError, match="未配置"):
        await empty.get()

    provider = FakeVectorProvider()
    manager = VectorStoreManager(
        _settings("knowledge", default="knowledge"),
        providers=VectorProviderRegistry((provider,)),
    )
    await manager.get()
    await manager.aclose()

    with pytest.raises(RuntimeError, match="已经关闭"):
        await manager.get()


def test_default_registry_contains_every_builtin_driver_and_can_be_extended() -> None:
    assert DEFAULT_VECTOR_PROVIDERS.drivers == ("milvus", "chroma", "elasticsearch")
    extended = DEFAULT_VECTOR_PROVIDERS.extended(FakeVectorProvider())
    assert extended.drivers == ("milvus", "chroma", "elasticsearch", "fake")


def test_registry_rejects_duplicate_driver() -> None:
    with pytest.raises(VectorConfigurationError, match="重复注册"):
        VectorProviderRegistry((FakeVectorProvider(), FakeVectorProvider()))
