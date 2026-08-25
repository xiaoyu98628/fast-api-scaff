import pytest

from app.bootstrap.app import create_app
from app.config.app import AppSettings
from app.config.cache import CacheSettings
from app.config.cors import CorsSettings
from app.config.database import DatabaseSettings
from app.config.settings import Settings
from app.infrastructure.cache.errors import CacheConfigurationError


@pytest.mark.asyncio
async def test_invalid_cache_configuration_blocks_application_startup() -> None:
    settings = Settings(
        app=AppSettings(_env_file=None),
        database=DatabaseSettings(_env_file=None),
        cache=CacheSettings(
            default="broken",
            namespace="test",
            connections={"broken": {"driver": "memcached"}},
            _env_file=None,
        ),
        cors=CorsSettings(_env_file=None),
    )

    app = create_app(settings)

    with pytest.raises(CacheConfigurationError, match="broken"):
        async with app.router.lifespan_context(app):
            pass


@pytest.mark.asyncio
async def test_unreachable_cache_does_not_block_application_startup() -> None:
    settings = Settings(
        app=AppSettings(_env_file=None),
        database=DatabaseSettings(_env_file=None),
        cache=CacheSettings(
            default="main",
            namespace="test",
            connections={"main": {"driver": "redis", "host": "127.0.0.1", "port": 1}},
            _env_file=None,
        ),
        cors=CorsSettings(_env_file=None),
    )
    app = create_app(settings)

    async with app.router.lifespan_context(app):
        assert app.state.container.caches.is_initialized("main") is False
