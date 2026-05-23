from sqlalchemy import URL
from sqlalchemy.engine import Engine

from app.infrastructure.database.connectors.factory import ConnectionFactory
from config.config import config
from config.database import DatabaseConfig


def _resolve_name(name: str | None, database_config: DatabaseConfig) -> str:
    return name or database_config.connection


def sync_url(name: str | None = None, *, hide_password: bool = False) -> str:
    """返回同步连接 URL 字符串，供 Alembic 等迁移工具使用。"""
    database_config = config().database
    connection_name = _resolve_name(name, database_config)
    connection_config = database_config.configuration(connection_name)
    url = ConnectionFactory().create_connector(connection_config.driver).make_sync_url(connection_config)
    if isinstance(url, URL):
        return url.render_as_string(hide_password=hide_password)
    return str(url)


def sync_engine(name: str | None = None) -> Engine:
    """创建同步 Engine，供迁移脚本或命令行工具使用。"""
    database_config = config().database
    connection_name = _resolve_name(name, database_config)
    connection_config = database_config.configuration(connection_name)
    return ConnectionFactory().create_connector(connection_config.driver).connect_sync(
        connection_config,
        database_config=database_config,
    )
