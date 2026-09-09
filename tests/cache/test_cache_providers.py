"""验证缓存 Provider 注册、替换和配置准备。"""

from functools import partial

import pytest

from app.bootstrap.build import build_application_container
from app.bootstrap.http.application import create_app
from app.config.app import AppSettings
from app.config.cache import CacheSettings
from app.config.cors import CorsSettings
from app.config.database import DatabaseSettings
from app.config.settings import Settings
from app.infrastructure.cache.errors import CacheConfigurationError
from app.infrastructure.cache.manager import CacheManager
from app.infrastructure.cache.providers.registry import DEFAULT_CACHE_PROVIDERS, CacheProviderRegistry
from tests.cache.fakes import FakeCacheProvider


def test_default_registry_contains_builtin_drivers() -> None:
    assert DEFAULT_CACHE_PROVIDERS.drivers == ("redis", "memcached")


def test_registry_rejects_duplicate_driver() -> None:
    with pytest.raises(CacheConfigurationError, match="重复注册"):
        CacheProviderRegistry((FakeCacheProvider(), FakeCacheProvider()))


@pytest.mark.parametrize("raw_config", [{}, {"driver": "unknown"}, {"driver": "memory"}])
def test_registry_rejects_missing_or_unknown_driver(raw_config: dict[str, object]) -> None:
    with pytest.raises(CacheConfigurationError):
        DEFAULT_CACHE_PROVIDERS.prepare(raw_config)


@pytest.mark.asyncio
async def test_manager_accepts_extended_provider_registry() -> None:
    providers = DEFAULT_CACHE_PROVIDERS.extended(FakeCacheProvider("custom"))
    settings = CacheSettings(
        default="main",
        namespace="test",
        connections={"main": {"driver": "custom", "key_prefix": "custom"}},
        _env_file=None,
    )
    manager = CacheManager(settings, providers=providers)

    cache = await manager.get()
    await cache.set("key", b"value")

    assert await cache.get("key") == b"value"
    assert "custom" not in DEFAULT_CACHE_PROVIDERS.drivers
    await manager.aclose()


@pytest.mark.asyncio
async def test_application_container_accepts_extended_provider_registry() -> None:
    providers = DEFAULT_CACHE_PROVIDERS.extended(FakeCacheProvider("custom"))
    settings = Settings(
        app=AppSettings(_env_file=None),
        database=DatabaseSettings(_env_file=None),
        cache=CacheSettings(
            default="main",
            namespace="test",
            connections={"main": {"driver": "custom"}},
            _env_file=None,
        ),
        cors=CorsSettings(_env_file=None),
    )
    app = create_app(
        settings,
        container_builder=partial(
            build_application_container,
            cache_providers=providers,
        ),
    )

    async with app.router.lifespan_context(app):
        cache = await app.state.container.caches.get()
        await cache.set("key", b"value")

        assert await cache.get("key") == b"value"
