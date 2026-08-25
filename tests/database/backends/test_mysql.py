from app.config.database import MySQLConnectionSettings
from app.infrastructure.database.backends.mysql import build_mysql_engine_spec


def test_mysql_engine_spec_contains_async_driver_and_pool_options() -> None:
    settings = MySQLConnectionSettings(
        driver="mysql",
        host="db.example.com",
        port=3307,
        database="application",
        username="app",
        password="secret",
        charset="utf8mb4",
        echo=True,
        pool_size=7,
        max_overflow=9,
        pool_pre_ping=False,
        pool_recycle=1200,
    )

    spec = build_mysql_engine_spec(settings)

    assert spec.url.drivername == "mysql+asyncmy"
    assert spec.url.username == "app"
    assert spec.url.password == "secret"
    assert spec.url.host == "db.example.com"
    assert spec.url.port == 3307
    assert spec.url.database == "application"
    assert dict(spec.url.query) == {"charset": "utf8mb4"}
    assert "secret" not in str(spec.url)
    assert spec.options == {
        "echo": True,
        "pool_size": 7,
        "max_overflow": 9,
        "pool_pre_ping": False,
        "pool_recycle": 1200,
    }
