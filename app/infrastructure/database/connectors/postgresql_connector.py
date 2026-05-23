from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.infrastructure.database.connectors.connector import Connector
from config.database import DatabaseConfig, DbDriver


class PostgresqlConnector(Connector):
    driver = DbDriver.POSTGRESQL

    def connect(self, database_config: DatabaseConfig) -> AsyncEngine:
        url = database_config.async_connections[self.driver]
        return create_async_engine(
            url,
            echo=database_config.echo,
            pool_size=database_config.pool_size,
            max_overflow=database_config.max_overflow,
        )
