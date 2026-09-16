"""验证限流配置、Redis 能力约束与延迟资源装配。"""

import pytest
from pydantic import ValidationError

from app.bootstrap.build import build_application_container
from app.config.app import AppSettings
from app.config.cache import CacheSettings
from app.config.cors import CorsSettings
from app.config.database import DatabaseSettings
from app.config.rate_limit import RateLimitSettings
from app.config.settings import Settings, load_settings
from app.infrastructure.cache.errors import CacheConfigurationError


def build_settings(*, enabled: bool = True, driver: str = "redis") -> Settings:
    return Settings(
        app=AppSettings(_env_file=None),
        database=DatabaseSettings(_env_file=None),
        cache=CacheSettings(
            namespace="test",
            default="limits",
            connections={"limits": {"driver": driver}},
            _env_file=None,
        ),
        cors=CorsSettings(_env_file=None),
        rate_limit=RateLimitSettings(enabled=enabled, _env_file=None),
    )


def test_defaults_and_environment_loading(monkeypatch: pytest.MonkeyPatch) -> None:
    defaults = RateLimitSettings(_env_file=None)
    assert (defaults.enabled, defaults.max_requests, defaults.window_seconds, defaults.fail_open) == (False, 1000, 60, False)
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_MAX_REQUESTS", "2000")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "120")
    load_settings.cache_clear()
    try:
        settings = load_settings().rate_limit
        assert (settings.enabled, settings.max_requests, settings.window_seconds) == (True, 2000, 120)
    finally:
        load_settings.cache_clear()


@pytest.mark.parametrize("count,window", [(0, 60), (1_000_001, 60), (1000, 0), (1000, 86_401)])
def test_invalid_limits(count: int, window: int) -> None:
    with pytest.raises(ValidationError):
        RateLimitSettings(max_requests=count, window_seconds=window, _env_file=None)


@pytest.mark.asyncio
async def test_enabled_limiter_does_not_initialize_redis() -> None:
    container = build_application_container(build_settings())
    try:
        assert container.rate_limiter is not None
        assert not container.caches.is_initialized("limits")
    finally:
        await container.aclose()


def test_enabled_limiter_rejects_memcached() -> None:
    with pytest.raises(CacheConfigurationError, match="Redis"):
        build_application_container(build_settings(driver="memcached"))


@pytest.mark.asyncio
async def test_disabled_limiter_does_not_require_redis() -> None:
    container = build_application_container(build_settings(enabled=False, driver="memcached"))
    try:
        assert container.rate_limiter is None
        assert not container.caches.is_initialized("limits")
    finally:
        await container.aclose()
