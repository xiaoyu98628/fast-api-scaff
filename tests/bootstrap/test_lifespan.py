import logging
from functools import partial

import pytest

from app.bootstrap.app import create_app
from app.bootstrap.container import ApplicationContainer
from app.bootstrap.logging import ApplicationLogEvent
from app.config.app import AppSettings
from app.config.cache import CacheSettings
from app.config.cors import CorsSettings
from app.config.database import DatabaseSettings
from app.config.settings import Settings
from app.contexts.user_management.application.service import UserApplicationService
from app.contexts.user_management.infrastructure.persistence.unit_of_work import SqlAlchemyUserUnitOfWork
from app.infrastructure.cache.manager import CacheManager
from app.infrastructure.database.manager import DatabaseManager


def build_settings() -> Settings:
    return Settings(
        app=AppSettings(_env_file=None),
        database=DatabaseSettings(_env_file=None),
        cache=CacheSettings(_env_file=None),
        cors=CorsSettings(_env_file=None),
    )


@pytest.mark.asyncio
async def test_application_lifecycle_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    app = create_app(build_settings())
    caplog.set_level(logging.INFO, logger="app.bootstrap.lifecycle")

    async with app.router.lifespan_context(app):
        pass

    events = [getattr(record, "event", None) for record in caplog.records]
    assert events == [
        ApplicationLogEvent.STARTING,
        ApplicationLogEvent.STARTED,
        ApplicationLogEvent.STOPPING,
        ApplicationLogEvent.STOPPED,
    ]


@pytest.mark.asyncio
async def test_application_startup_failure_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    settings = build_settings()

    async def fail_startup() -> None:
        raise RuntimeError("startup failed")

    databases = DatabaseManager(settings.database)
    container = ApplicationContainer(
        databases=databases,
        caches=CacheManager(settings.cache),
        users=UserApplicationService(unit_of_work_factory=partial(SqlAlchemyUserUnitOfWork, databases)),
        startup_callbacks=(fail_startup,),
    )
    app = create_app(settings, container_builder=lambda _settings: container)
    caplog.set_level(logging.INFO, logger="app.bootstrap.lifecycle")

    with pytest.raises(RuntimeError, match="startup failed"):
        async with app.router.lifespan_context(app):
            pass

    events = [getattr(record, "event", None) for record in caplog.records]
    assert ApplicationLogEvent.START_FAILED in events
    assert ApplicationLogEvent.STOPPED in events
