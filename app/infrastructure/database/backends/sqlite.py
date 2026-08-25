from sqlalchemy import URL

from app.config.database import SQLiteConnectionSettings
from app.infrastructure.database.backends.spec import DatabaseEngineSpec


def build_sqlite_engine_spec(settings: SQLiteConnectionSettings) -> DatabaseEngineSpec:
    """构建 SQLite 异步 Engine 配置，不创建连接。"""
    url = URL.create(
        drivername="sqlite+aiosqlite",
        database=settings.resolved_database,
    )

    return DatabaseEngineSpec(
        url=url,
        options={"echo": settings.echo},
    )
