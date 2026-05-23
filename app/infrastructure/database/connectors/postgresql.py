from app.infrastructure.database.connectors.connector import BaseConnector
from config.database import DatabaseConfig, DbDriver


class PostgresqlConnector(BaseConnector):
    driver = DbDriver.POSTGRESQL

    def engine_options(self, database_config: DatabaseConfig) -> dict:
        return {
            "echo": database_config.echo,
            "pool_size": database_config.pool_size,
            "max_overflow": database_config.max_overflow,
        }
