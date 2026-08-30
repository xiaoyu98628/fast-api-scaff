import pytest

from app.bootstrap.app import create_app
from app.config.app import AppSettings
from app.config.cache import CacheSettings
from app.config.cors import CorsSettings
from app.config.database import DatabaseSettings
from app.config.settings import Settings
from app.contexts.user.application.service import UserApplicationService
from app.contexts.user.composition import UserContext
from app.infrastructure.cache.manager import CacheManager
from app.infrastructure.database.manager import DatabaseManager


@pytest.mark.asyncio
async def test_empty_database_config_does_not_block_application_startup() -> None:
    settings = Settings(
        app=AppSettings(_env_file=None),
        database=DatabaseSettings(_env_file=None),
        cache=CacheSettings(_env_file=None),
        cors=CorsSettings(_env_file=None),
    )
    app = create_app(settings)

    async with app.router.lifespan_context(app):
        container = app.state.container

        assert isinstance(container.databases, DatabaseManager)
        assert container.databases.connection_names == ()
        assert isinstance(container.caches, CacheManager)
        assert container.caches.connection_names == ()
        assert isinstance(container.users, UserContext)
        assert isinstance(container.users.service, UserApplicationService)
