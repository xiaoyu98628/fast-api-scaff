"""验证缓存 Provider 注册、替换和配置准备。"""

import subprocess
import sys
from functools import partial

import pytest

from app.bootstrap.build import build_application_container
from app.bootstrap.http.application import create_app
from app.config.app import AppSettings
from app.config.auth import AuthSettings
from app.config.cache import CacheSettings
from app.config.cors import CorsSettings
from app.config.database import DatabaseSettings
from app.config.settings import Settings
from app.infrastructure.cache.errors import CacheConfigurationError
from app.infrastructure.cache.manager import CacheManager
from app.infrastructure.cache.providers.registry import DEFAULT_CACHE_PROVIDERS, CacheProviderRegistry
from app.runtime.paths import PROJECT_ROOT
from tests.cache.fakes import FakeCacheProvider


def test_default_registry_contains_builtin_drivers() -> None:
    assert DEFAULT_CACHE_PROVIDERS.drivers == ("redis", "memcached")


def test_cache_drivers_are_imported_only_when_the_selected_resource_is_created() -> None:
    script = """
import asyncio
import sys
from app.config.cache import CacheSettings
from app.infrastructure.cache.manager import CacheManager

manager = CacheManager(CacheSettings(
    default="session",
    namespace="test",
    connections={
        "session": {"driver": "redis"},
        "page": {"driver": "memcached"},
    },
    _env_file=None,
))
assert "redis" not in sys.modules
assert "memcachio" not in sys.modules
asyncio.run(manager.get("session"))
assert "redis" in sys.modules
assert "memcachio" not in sys.modules
asyncio.run(manager.aclose())
"""

    result = subprocess.run([sys.executable, "-c", script], cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=10)

    assert result.returncode == 0, result.stderr


def test_missing_cache_driver_dependency_has_stable_configuration_error() -> None:
    script = """
import asyncio
import builtins
from app.config.cache import CacheSettings
from app.infrastructure.cache.errors import CacheConfigurationError
from app.infrastructure.cache.manager import CacheManager

manager = CacheManager(CacheSettings(
    default="session",
    namespace="test",
    connections={"session": {"driver": "redis"}},
    _env_file=None,
))
original_import = builtins.__import__
def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "redis" or name.startswith("redis."):
        raise ModuleNotFoundError("blocked redis dependency")
    return original_import(name, globals, locals, fromlist, level)
builtins.__import__ = guarded_import
try:
    asyncio.run(manager.get())
except CacheConfigurationError as error:
    assert "客户端依赖无法加载" in str(error)
else:
    raise AssertionError("missing Redis dependency was accepted")
"""

    result = subprocess.run([sys.executable, "-c", script], cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=10)

    assert result.returncode == 0, result.stderr


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


def test_login_limiter_rejects_memcached_during_container_composition() -> None:
    settings = Settings(
        app=AppSettings(_env_file=None),
        auth=AuthSettings(login_limit_cache="security", _env_file=None),
        database=DatabaseSettings(_env_file=None),
        cache=CacheSettings(
            namespace="test",
            connections={"security": {"driver": "memcached"}},
            _env_file=None,
        ),
        cors=CorsSettings(_env_file=None),
    )

    with pytest.raises(CacheConfigurationError, match="不支持所需的 Redis 功能"):
        build_application_container(settings)
