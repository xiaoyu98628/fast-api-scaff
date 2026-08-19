import pytest

from app.bootstrap.app import create_app
from app.config.app import AppSettings
from app.config.cache import CacheSettings
from app.config.database import DatabaseSettings
from app.config.settings import Settings


@pytest.mark.asyncio
async def test_invalid_cache_connection_does_not_block_application_startup() -> None:
    settings = Settings(
        app=AppSettings(_env_file=None),
        database=DatabaseSettings(_env_file=None),
        cache=CacheSettings(
            default="broken",
            connections={"broken": {"driver": "memcached"}},
            _env_file=None,
        ),
    )
    app = create_app(settings)

    async with app.router.lifespan_context(app):
        assert app.state.container.caches.is_initialized("broken") is False
