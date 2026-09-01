import pytest

from app.bootstrap.container import ApplicationContainer
from app.config.app import AppSettings
from app.config.cache import CacheSettings
from app.config.cors import CorsSettings
from app.config.database import DatabaseSettings
from app.config.http import HttpSettings
from app.config.settings import Settings
from app.contexts.user.composition import build_user_context
from app.infrastructure.cache.manager import CacheManager
from app.infrastructure.database.manager import DatabaseManager
from app.infrastructure.http.manager import HttpClientManager
from app.interfaces.console.application import ConsoleApplication
from app.interfaces.console.context import ConsoleContext


def build_settings() -> Settings:
    return Settings(
        app=AppSettings(name="console-test", _env_file=None),
        database=DatabaseSettings(_env_file=None),
        cache=CacheSettings(_env_file=None),
        cors=CorsSettings(_env_file=None),
    )


def build_container(settings: Settings, events: list[str]) -> ApplicationContainer:
    async def start() -> None:
        events.append("start")

    async def stop() -> None:
        events.append("stop")

    databases = DatabaseManager(settings.database)
    caches = CacheManager(settings.cache)
    http = HttpClientManager(HttpSettings(_env_file=None))
    return ApplicationContainer(
        databases=databases,
        caches=caches,
        http=http,
        users=build_user_context(databases),
        startup_callbacks=(start,),
        async_shutdown_callbacks=(stop, databases.aclose, caches.aclose, http.aclose),
    )


def test_console_application_provides_context_and_closes_runtime() -> None:
    settings = build_settings()
    events: list[str] = []
    console = ConsoleApplication(
        settings_loader=lambda: settings,
        container_builder=lambda active_settings: build_container(active_settings, events),
        logging_configurer=lambda _settings: events.append("logging"),
    )

    async def operation(context: ConsoleContext) -> str:
        assert context.settings is settings
        events.append("operation")
        return context.settings.app.name

    assert console.run(operation) == "console-test"
    assert events == ["logging", "start", "operation", "stop"]


def test_console_application_closes_runtime_when_operation_fails() -> None:
    settings = build_settings()
    events: list[str] = []
    console = ConsoleApplication(
        settings_loader=lambda: settings,
        container_builder=lambda active_settings: build_container(active_settings, events),
        logging_configurer=lambda _settings: events.append("logging"),
    )

    async def fail(_context: ConsoleContext) -> None:
        events.append("operation")
        raise RuntimeError("operation failed")

    with pytest.raises(RuntimeError, match="operation failed"):
        console.run(fail)

    assert events == ["logging", "start", "operation", "stop"]
