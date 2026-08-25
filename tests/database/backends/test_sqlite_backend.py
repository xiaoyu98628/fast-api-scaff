from app.config.database import SQLiteConnectionSettings
from app.infrastructure.database.backends.sqlite import build_sqlite_engine_spec


def test_sqlite_engine_spec_contains_only_supported_options() -> None:
    settings = SQLiteConnectionSettings(
        driver="sqlite",
        database=":memory:",
        echo=True,
    )

    spec = build_sqlite_engine_spec(settings)

    assert spec.url.drivername == "sqlite+aiosqlite"
    assert spec.url.database == ":memory:"
    assert spec.options == {"echo": True}
