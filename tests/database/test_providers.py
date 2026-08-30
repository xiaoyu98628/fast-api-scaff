import pytest
from sqlalchemy import URL

from app.bootstrap.build import build_application_container
from app.config.app import AppSettings
from app.config.cache import CacheSettings
from app.config.cors import CorsSettings
from app.config.database import DatabaseSettings
from app.config.settings import Settings
from app.infrastructure.database.connections.spec import DatabaseEngineSpec
from app.infrastructure.database.contracts.provider import DatabaseResourceDefinition
from app.infrastructure.database.errors import DatabaseConfigurationError
from app.infrastructure.database.manager import DatabaseManager
from app.infrastructure.database.providers.mysql import MySQLDatabaseProvider
from app.infrastructure.database.providers.postgresql import PostgreSQLDatabaseProvider
from app.infrastructure.database.providers.registry import DEFAULT_DATABASE_PROVIDERS, DatabaseProviderRegistry
from app.infrastructure.database.providers.sqlite import SQLiteDatabaseProvider


class CustomDatabaseProvider:
    drivers = ("custom",)

    def prepare(self, raw_config: dict[str, object]) -> DatabaseResourceDefinition:
        return DatabaseResourceDefinition(
            engine_spec=DatabaseEngineSpec(
                url=URL.create("sqlite+aiosqlite", database=":memory:"),
                options={},
            ),
        )


def test_default_registry_contains_builtin_drivers_and_aliases() -> None:
    assert DEFAULT_DATABASE_PROVIDERS.drivers == ("mysql", "postgresql", "pgsql", "sqlite")


def test_registry_rejects_duplicate_driver() -> None:
    with pytest.raises(DatabaseConfigurationError, match="重复注册"):
        DatabaseProviderRegistry((SQLiteDatabaseProvider(), SQLiteDatabaseProvider()))


@pytest.mark.parametrize("raw_config", [{}, {"driver": "unknown"}])
def test_registry_rejects_missing_or_unknown_driver(raw_config: dict[str, object]) -> None:
    with pytest.raises(DatabaseConfigurationError):
        DEFAULT_DATABASE_PROVIDERS.prepare(raw_config)


def test_mysql_provider_builds_asyncmy_engine_spec() -> None:
    definition = MySQLDatabaseProvider().prepare(
        {
            "driver": "mysql",
            "host": "db.example.com",
            "port": 3307,
            "database": "application",
            "username": "app",
            "password": "secret",
            "charset": "utf8mb4",
            "echo": True,
            "pool_size": 7,
            "max_overflow": 9,
            "pool_pre_ping": False,
            "pool_recycle": 1200,
        }
    )
    spec = definition.engine_spec

    assert spec.url.drivername == "mysql+asyncmy"
    assert spec.url.username == "app"
    assert spec.url.password == "secret"
    assert spec.url.host == "db.example.com"
    assert spec.url.port == 3307
    assert spec.url.database == "application"
    assert dict(spec.url.query) == {"charset": "utf8mb4"}
    assert "secret" not in str(spec.url)
    assert spec.options == {
        "pool_size": 7,
        "max_overflow": 9,
        "pool_pre_ping": False,
        "pool_recycle": 1200,
    }
    assert spec.log_queries is True
    assert spec.slow_query_ms == 500


@pytest.mark.parametrize("driver", ["postgresql", "pgsql"])
def test_postgresql_provider_supports_both_driver_names(driver: str) -> None:
    definition = PostgreSQLDatabaseProvider().prepare(
        {
            "driver": driver,
            "host": "db.example.com",
            "port": 5433,
            "database": "application",
            "username": "app",
            "password": "secret",
            "echo": True,
            "pool_size": 7,
            "max_overflow": 9,
            "pool_pre_ping": False,
            "pool_recycle": 1200,
        }
    )
    spec = definition.engine_spec

    assert spec.url.drivername == "postgresql+asyncpg"
    assert spec.url.username == "app"
    assert spec.url.password == "secret"
    assert spec.url.host == "db.example.com"
    assert spec.url.port == 5433
    assert spec.url.database == "application"
    assert "secret" not in str(spec.url)
    assert spec.options == {
        "pool_size": 7,
        "max_overflow": 9,
        "pool_pre_ping": False,
        "pool_recycle": 1200,
    }
    assert spec.log_queries is True
    assert spec.slow_query_ms == 500


def test_sqlite_provider_builds_supported_engine_spec() -> None:
    definition = SQLiteDatabaseProvider().prepare(
        {
            "driver": "sqlite",
            "database": ":memory:",
            "echo": True,
        }
    )

    assert definition.engine_spec.url.drivername == "sqlite+aiosqlite"
    assert definition.engine_spec.url.database == ":memory:"
    assert definition.engine_spec.options == {}
    assert definition.engine_spec.log_queries is True
    assert definition.engine_spec.slow_query_ms == 500


@pytest.mark.asyncio
async def test_manager_accepts_extended_provider_registry() -> None:
    providers = DEFAULT_DATABASE_PROVIDERS.extended(CustomDatabaseProvider())
    settings = DatabaseSettings(
        default="main",
        connections={"main": {"driver": "custom"}},
        _env_file=None,
    )
    manager = DatabaseManager(settings, providers=providers)

    engine = await manager.get_engine()

    assert engine.url.drivername == "sqlite+aiosqlite"
    assert "custom" not in DEFAULT_DATABASE_PROVIDERS.drivers
    await manager.aclose()


@pytest.mark.asyncio
async def test_application_container_accepts_extended_database_provider_registry() -> None:
    providers = DEFAULT_DATABASE_PROVIDERS.extended(CustomDatabaseProvider())
    settings = Settings(
        app=AppSettings(_env_file=None),
        database=DatabaseSettings(
            default="main",
            connections={"main": {"driver": "custom"}},
            _env_file=None,
        ),
        cache=CacheSettings(_env_file=None),
        cors=CorsSettings(_env_file=None),
    )
    container = build_application_container(
        settings,
        database_providers=providers,
    )

    engine = await container.databases.get_engine()

    assert engine.url.drivername == "sqlite+aiosqlite"
    await container.aclose()
