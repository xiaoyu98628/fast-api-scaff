import pytest

from app.config.database import DatabaseSettings, SQLiteConnectionSettings
from app.infrastructure.database.connection import (
    resolve_database_connection,
    validate_database_connection,
)
from app.infrastructure.database.errors import DatabaseConfigurationError


def test_validate_database_connection_parses_raw_config() -> None:
    settings = validate_database_connection(
        "main",
        {"driver": "sqlite", "database": ":memory:"},
    )

    assert isinstance(settings, SQLiteConnectionSettings)
    assert settings.database == ":memory:"


def test_validate_database_connection_reports_connection_name() -> None:
    with pytest.raises(DatabaseConfigurationError, match="broken"):
        validate_database_connection("broken", {"driver": "mysql"})


def test_resolve_database_connection_uses_default_or_named_connection() -> None:
    settings = DatabaseSettings(
        default="main",
        connections={
            "main": {"driver": "sqlite", "database": ":memory:"},
            "reporting": {"driver": "sqlite", "database": "reporting.sqlite"},
        },
        _env_file=None,
    )

    default = resolve_database_connection(settings)
    reporting = resolve_database_connection(settings, "reporting")

    assert isinstance(default, SQLiteConnectionSettings)
    assert default.database == ":memory:"
    assert isinstance(reporting, SQLiteConnectionSettings)
    assert reporting.database == "reporting.sqlite"


def test_resolve_database_connection_requires_default_connection() -> None:
    settings = DatabaseSettings(_env_file=None)

    with pytest.raises(DatabaseConfigurationError, match="默认数据库连接"):
        resolve_database_connection(settings)


def test_resolve_database_connection_reports_missing_named_connection() -> None:
    settings = DatabaseSettings(_env_file=None)

    with pytest.raises(DatabaseConfigurationError, match="reporting"):
        resolve_database_connection(settings, "reporting")
