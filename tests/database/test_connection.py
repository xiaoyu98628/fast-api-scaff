import pytest

from app.config.database import DatabaseSettings
from app.infrastructure.database.connections.resolver import (
    resolve_database_definition,
    validate_database_definition,
)
from app.infrastructure.database.errors import DatabaseConfigurationError
from app.infrastructure.database.orm.prefix import resolve_database_table_prefix


def test_validate_database_definition_parses_raw_config() -> None:
    definition = validate_database_definition(
        "main",
        {"driver": "sqlite", "database": ":memory:"},
    )

    assert definition.engine_spec.url.drivername == "sqlite+aiosqlite"
    assert definition.engine_spec.url.database == ":memory:"


def test_validate_database_definition_reports_connection_name() -> None:
    with pytest.raises(DatabaseConfigurationError, match="broken"):
        validate_database_definition("broken", {"driver": "mysql"})


def test_resolve_database_definition_uses_default_or_named_connection() -> None:
    settings = DatabaseSettings(
        default="main",
        connections={
            "main": {"driver": "sqlite", "database": ":memory:"},
            "reporting": {"driver": "sqlite", "database": "reporting.sqlite"},
        },
        _env_file=None,
    )

    default = resolve_database_definition(settings)
    reporting = resolve_database_definition(settings, "reporting")

    assert default.engine_spec.url.database == ":memory:"
    assert reporting.engine_spec.url.database is not None
    assert reporting.engine_spec.url.database.endswith("reporting.sqlite")


def test_resolve_database_definition_requires_default_connection() -> None:
    settings = DatabaseSettings(_env_file=None)

    with pytest.raises(DatabaseConfigurationError, match="默认数据库连接"):
        resolve_database_definition(settings)


def test_resolve_database_definition_reports_missing_named_connection() -> None:
    settings = DatabaseSettings(_env_file=None)

    with pytest.raises(DatabaseConfigurationError, match="reporting"):
        resolve_database_definition(settings, "reporting")


def test_resolve_database_table_prefix_does_not_validate_other_connection_fields() -> None:
    settings = DatabaseSettings(
        connections={"main": {"driver": "mysql", "table_prefix": "main_"}},
        _env_file=None,
    )

    assert resolve_database_table_prefix(settings, "main") == "main_"


def test_resolve_database_table_prefix_defaults_to_empty_string() -> None:
    settings = DatabaseSettings(_env_file=None)

    assert resolve_database_table_prefix(settings, "main") == ""


def test_resolve_database_table_prefix_reports_invalid_value() -> None:
    settings = DatabaseSettings(
        connections={"main": {"table_prefix": "invalid-prefix_"}},
        _env_file=None,
    )

    with pytest.raises(DatabaseConfigurationError, match="main.*表前缀"):
        resolve_database_table_prefix(settings, "main")
