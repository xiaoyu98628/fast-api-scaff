from sqlalchemy import URL

from app.infrastructure.database.connectors.connector import BaseConnector
from config.database import ConnectionConfig, DatabaseConfig


class MysqlConnector(BaseConnector):
    def make_url(self, connection_config: ConnectionConfig) -> URL:
        query = {"charset": connection_config.charset} if connection_config.charset else {}
        return URL.create(
            drivername="mysql+aiomysql",
            username=connection_config.username or None,
            password=connection_config.password or None,
            host=connection_config.host,
            port=connection_config.port,
            database=connection_config.database,
            query=query,
        )

    def engine_options(self, connection_config: ConnectionConfig, database_config: DatabaseConfig) -> dict:
        return {
            "echo": database_config.echo,
            "pool_size": database_config.pool_size,
            "max_overflow": database_config.max_overflow,
        }
