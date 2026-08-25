from sqlalchemy import URL

from app.config.database import PostgreSQLConnectionSettings
from app.infrastructure.database.backends.spec import DatabaseEngineSpec


def build_postgresql_engine_spec(settings: PostgreSQLConnectionSettings) -> DatabaseEngineSpec:
    """构建 PostgreSQL 异步 Engine 配置，不创建连接。"""
    url = URL.create(
        drivername="postgresql+asyncpg",
        username=settings.username,
        password=settings.password.get_secret_value(),
        host=settings.host,
        port=settings.port,
        database=settings.database,
    )

    return DatabaseEngineSpec(
        url=url,
        options={
            "echo": settings.echo,
            "pool_size": settings.pool_size,
            "max_overflow": settings.max_overflow,
            "pool_pre_ping": settings.pool_pre_ping,
            "pool_recycle": settings.pool_recycle,
        },
    )
