from typing import Literal

import pytest

from app.config.database import PostgreSQLConnectionSettings
from app.infrastructure.database.backends.postgresql import build_postgresql_engine_spec


@pytest.mark.parametrize("driver", ["postgresql", "pgsql"])
def test_postgresql_engine_spec_contains_async_driver_and_pool_options(
    driver: Literal["postgresql", "pgsql"],
) -> None:
    settings = PostgreSQLConnectionSettings(
        driver=driver,
        host="db.example.com",
        port=5433,
        database="application",
        username="app",
        password="secret",
        echo=True,
        pool_size=7,
        max_overflow=9,
        pool_pre_ping=False,
        pool_recycle=1200,
    )

    spec = build_postgresql_engine_spec(settings)

    assert spec.url.drivername == "postgresql+asyncpg"
    assert spec.url.username == "app"
    assert spec.url.password == "secret"
    assert spec.url.host == "db.example.com"
    assert spec.url.port == 5433
    assert spec.url.database == "application"
    assert "secret" not in str(spec.url)
    assert spec.options == {
        "echo": True,
        "pool_size": 7,
        "max_overflow": 9,
        "pool_pre_ping": False,
        "pool_recycle": 1200,
    }
