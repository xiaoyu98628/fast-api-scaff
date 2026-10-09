"""验证多驱动数据库配置模型和严格字段约束。"""

import os

import pytest
from pydantic import ValidationError

from app.config.database import DatabaseSettings, SQLiteDatabaseSettings
from app.infrastructure.database.connections.resolver import resolve_database_definition
from app.runtime.paths import PROJECT_ROOT, STORAGE_DIR


def test_raw_settings_do_not_validate_connection_semantics() -> None:
    settings = DatabaseSettings(
        default="missing",
        connections={"broken": {"driver": "mysql"}},
        _env_file=None,
    )

    assert settings.default == "missing"
    assert settings.connections == {"broken": {"driver": "mysql"}}


def test_nested_environment_is_loaded_as_raw_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DB_DEFAULT", "main")
    monkeypatch.setenv("DB_CONNECTIONS__MAIN__DRIVER", "sqlite")
    monkeypatch.setenv("DB_CONNECTIONS__MAIN__DATABASE", ":memory:")

    settings = DatabaseSettings(_env_file=None)

    assert settings.default == "main"
    assert settings.connections == {
        "main": {
            "driver": "sqlite",
            "database": ":memory:",
        }
    }


def test_driver_defaults_are_loaded_and_overridden_by_named_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DB_CONNECTION_DEFAULTS__MYSQL__HOST", "mysql.internal")
    monkeypatch.setenv("DB_CONNECTION_DEFAULTS__MYSQL__PORT", "3307")
    monkeypatch.setenv("DB_CONNECTION_DEFAULTS__MYSQL__USERNAME", "common-user")
    monkeypatch.setenv("DB_CONNECTION_DEFAULTS__MYSQL__PASSWORD", "common-secret")
    monkeypatch.setenv("DB_CONNECTIONS__MAIN__DRIVER", "mysql")
    monkeypatch.setenv("DB_CONNECTIONS__MAIN__HOST", "mysql.override.internal")
    monkeypatch.setenv("DB_CONNECTIONS__MAIN__DATABASE", "application")

    settings = DatabaseSettings(_env_file=None)
    definition = resolve_database_definition(settings, "main")

    assert settings.connection_defaults == {
        "mysql": {
            "host": "mysql.internal",
            "port": 3307,
            "username": "common-user",
            "password": "common-secret",
        }
    }
    assert definition.engine_spec.url.host == "mysql.override.internal"
    assert definition.engine_spec.url.port == 3307
    assert definition.engine_spec.url.username == "common-user"
    assert definition.engine_spec.url.database == "application"


def test_driver_defaults_do_not_affect_other_drivers() -> None:
    settings = DatabaseSettings(
        connection_defaults={
            "mysql": {
                "host": "mysql.internal",
                "username": "common-user",
                "password": "common-secret",
            }
        },
        connections={"queue": {"driver": "sqlite", "database": ":memory:"}},
        _env_file=None,
    )

    definition = resolve_database_definition(settings, "queue")

    assert definition.engine_spec.url.drivername == "sqlite+aiosqlite"


def test_sample_environment_contains_valid_database_connections(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in tuple(os.environ):
        if name.startswith("DB_"):
            monkeypatch.delenv(name)

    settings = DatabaseSettings(_env_file=PROJECT_ROOT / "sample.env")

    assert settings.connections
    for name in settings.connections:
        definition = resolve_database_definition(settings, name)
        assert definition.engine_spec.url.drivername


@pytest.mark.parametrize(
    ("database", "expected"),
    [
        (":memory:", ":memory:"),
        ("data/database.sqlite", str(STORAGE_DIR / "data/database.sqlite")),
        ("/var/data/database.sqlite", "/var/data/database.sqlite"),
    ],
)
def test_sqlite_database_path_is_resolved_from_storage_directory(
    database: str,
    expected: str,
) -> None:
    settings = SQLiteDatabaseSettings(driver="sqlite", database=database)

    assert settings.resolved_database == expected


def test_database_driver_rejects_unknown_configuration_fields() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        SQLiteDatabaseSettings.model_validate(
            {
                "driver": "sqlite",
                "database": ":memory:",
                "table_prefix": "legacy_",
            }
        )
