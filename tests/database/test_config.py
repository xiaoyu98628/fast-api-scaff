import pytest
from pydantic import ValidationError

from app.config.database import DatabaseSettings, MySQLDatabaseSettings, PostgreSQLDatabaseSettings, SQLiteDatabaseSettings
from app.runtime.paths import STORAGE_DIR


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
    monkeypatch.setenv("DB_CONNECTIONS__MAIN__TABLE_PREFIX", "main_")

    settings = DatabaseSettings(_env_file=None)

    assert settings.default == "main"
    assert settings.connections == {
        "main": {
            "driver": "sqlite",
            "database": ":memory:",
            "table_prefix": "main_",
        }
    }


@pytest.mark.parametrize(
    "settings_type",
    [MySQLDatabaseSettings, PostgreSQLDatabaseSettings, SQLiteDatabaseSettings],
)
def test_all_database_drivers_default_to_empty_table_prefix(settings_type: type[object]) -> None:
    if settings_type is MySQLDatabaseSettings:
        settings = MySQLDatabaseSettings(
            driver="mysql",
            host="127.0.0.1",
            database="application",
            username="user",
            password="secret",
        )
    elif settings_type is PostgreSQLDatabaseSettings:
        settings = PostgreSQLDatabaseSettings(
            driver="postgresql",
            host="127.0.0.1",
            database="application",
            username="user",
            password="secret",
        )
    else:
        settings = SQLiteDatabaseSettings(driver="sqlite", database=":memory:")

    assert settings.table_prefix == ""


@pytest.mark.parametrize(
    "table_prefix",
    ["FastApi_", "fast-api_", "123_", "missing_separator"],
)
def test_table_prefix_rejects_unstable_identifier_fragments(table_prefix: str) -> None:
    with pytest.raises(ValidationError):
        SQLiteDatabaseSettings(
            driver="sqlite",
            database=":memory:",
            table_prefix=table_prefix,
        )


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
