import pytest

from app.config.database import DatabaseSettings, SQLiteConnectionSettings
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

    settings = DatabaseSettings(_env_file=None)

    assert settings.default == "main"
    assert settings.connections == {
        "main": {
            "driver": "sqlite",
            "database": ":memory:",
        }
    }


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
    settings = SQLiteConnectionSettings(driver="sqlite", database=database)

    assert settings.resolved_database == expected
