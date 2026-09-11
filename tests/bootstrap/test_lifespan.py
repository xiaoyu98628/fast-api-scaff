"""验证 FastAPI lifespan 的容器暴露和日志事件。"""

import logging
from dataclasses import replace

import pytest

from app.bootstrap.build import build_application_container
from app.bootstrap.http.application import create_app
from app.bootstrap.http.logging import ApplicationLogEvent
from app.config.app import AppSettings
from app.config.cache import CacheSettings
from app.config.cors import CorsSettings
from app.config.database import DatabaseSettings
from app.config.http import HttpSettings
from app.config.queue import QueueSettings
from app.config.settings import Settings
from app.config.vector import VectorSettings
from app.contexts.user.composition import build_user_context
from app.infrastructure.cache.manager import CacheManager
from app.infrastructure.database.manager import DatabaseManager
from app.infrastructure.http.manager import HttpClientManager
from app.infrastructure.queue.manager import QueueManager
from app.infrastructure.vector.manager import VectorStoreManager
from app.runtime.container import ApplicationContainer


def build_settings() -> Settings:
    return Settings(
        app=AppSettings(_env_file=None),
        database=DatabaseSettings(_env_file=None),
        cache=CacheSettings(_env_file=None),
        cors=CorsSettings(_env_file=None),
    )


@pytest.mark.asyncio
async def test_http_lifespan_does_not_initialize_queue() -> None:
    settings = build_settings().model_copy(
        update={
            "queue": QueueSettings(
                _env_file=None,
                default="main",
                connections={"main": {"driver": "redis", "host": "localhost"}},
            )
        }
    )
    container = build_application_container(settings)
    app = create_app(settings, container_builder=lambda _: container)

    async with app.router.lifespan_context(app):
        assert not container.queues.is_initialized()


@pytest.mark.asyncio
async def test_application_lifecycle_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    app = create_app(build_settings())
    caplog.set_level(logging.INFO, logger="app.bootstrap.lifecycle")

    async with app.router.lifespan_context(app):
        assert app.state.container is not None

    assert not hasattr(app.state, "container")

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
        queues=QueueManager(QueueSettings(_env_file=None), databases),
        databases=databases,
        caches=CacheManager(settings.cache),
        http=HttpClientManager(HttpSettings(_env_file=None)),
        vectors=VectorStoreManager(VectorSettings(_env_file=None)),
        users=build_user_context(databases),
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


@pytest.mark.asyncio
async def test_application_logs_base_exception_during_startup(caplog: pytest.LogCaptureFixture) -> None:
    settings = build_settings()

    class FatalStartup(BaseException):
        pass

    async def fail_startup() -> None:
        raise FatalStartup()

    container = build_application_container(settings)
    container = ApplicationContainer(
        queues=container.queues,
        databases=container.databases,
        caches=container.caches,
        http=container.http,
        vectors=container.vectors,
        users=container.users,
        startup_callbacks=(fail_startup,),
        async_shutdown_callbacks=container.async_shutdown_callbacks,
    )
    app = create_app(settings, container_builder=lambda _settings: container)
    caplog.set_level(logging.INFO, logger="app.bootstrap.lifecycle")

    with pytest.raises(FatalStartup):
        async with app.router.lifespan_context(app):
            pass

    events = [getattr(record, "event", None) for record in caplog.records]
    assert ApplicationLogEvent.START_FAILED in events
    assert ApplicationLogEvent.STOPPED in events


@pytest.mark.asyncio
async def test_application_clears_exposed_container_when_shutdown_fails(caplog: pytest.LogCaptureFixture) -> None:
    settings = build_settings()

    async def fail_shutdown() -> None:
        raise RuntimeError("shutdown failed")

    container = replace(
        build_application_container(settings),
        async_shutdown_callbacks=(fail_shutdown,),
    )
    app = create_app(settings, container_builder=lambda _settings: container)
    caplog.set_level(logging.INFO, logger="app.bootstrap.lifecycle")

    with pytest.raises(ExceptionGroup, match="shutdown callbacks failed"):
        async with app.router.lifespan_context(app):
            assert app.state.container is container

    assert not hasattr(app.state, "container")
    events = [getattr(record, "event", None) for record in caplog.records]
    assert ApplicationLogEvent.STOP_FAILED in events
