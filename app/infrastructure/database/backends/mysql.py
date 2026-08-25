from sqlalchemy import URL

from app.config.database import MySQLConnectionSettings
from app.infrastructure.database.backends.spec import DatabaseEngineSpec


def build_mysql_engine_spec(settings: MySQLConnectionSettings) -> DatabaseEngineSpec:
    """构建 MySQL 异步 Engine 配置，不创建连接。"""
    url = URL.create(
        drivername="mysql+asyncmy",
        username=settings.username,
        password=settings.password.get_secret_value(),
        host=settings.host,
        port=settings.port,
        database=settings.database,
        query={"charset": settings.charset},
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
