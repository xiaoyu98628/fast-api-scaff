from sqlalchemy import URL

from app.infrastructure.database.connectors.connector import BaseConnector
from config.database import ConnectionConfig, DatabaseConfig


class SqliteConnector(BaseConnector):
    def make_url(self, connection_config: ConnectionConfig) -> URL:
        return URL.create(
            drivername="sqlite+aiosqlite",
            database=connection_config.database,
        )

    def engine_options(self, connection_config: ConnectionConfig, database_config: DatabaseConfig) -> dict:
        return {"echo": database_config.echo}
