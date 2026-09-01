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
