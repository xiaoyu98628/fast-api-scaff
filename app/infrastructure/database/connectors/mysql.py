from sqlalchemy import URL

from app.infrastructure.database.connectors.connector import BaseConnector
from config.database import ConnectionConfig, DatabaseConfig


class MysqlConnector(BaseConnector):
    def _make_url(self, connection_config: ConnectionConfig, drivername: str) -> URL:
        query = {"charset": connection_config.charset} if connection_config.charset else {}
        return URL.create(
            drivername=drivername,
            username=connection_config.username or None,
            password=connection_config.password or None,
            host=connection_config.host,
            port=connection_config.port,
            database=connection_config.database,
            query=query,
        )

    def make_async_url(self, connection_config: ConnectionConfig) -> URL:
        return self._make_url(connection_config, "mysql+aiomysql")

    def make_sync_url(self, connection_config: ConnectionConfig) -> URL:
        return self._make_url(connection_config, "mysql+pymysql")

    def _driver_engine_options(self, connection_config: ConnectionConfig, database_config: DatabaseConfig) -> dict:
        return {
            "pool_recycle": 3600, # 回收连接（防止 MySQL 断开）
            "pool_pre_ping": True, # 心跳
        }
