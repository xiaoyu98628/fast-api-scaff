from sqlalchemy import URL

from app.infrastructure.database.connectors.connector import BaseConnector
from config.database import ConnectionConfig


class SqliteConnector(BaseConnector):
    def make_async_url(self, connection_config: ConnectionConfig) -> URL:
        return URL.create(
            drivername="sqlite+aiosqlite",
            database=connection_config.database,
        )

    def make_sync_url(self, connection_config: ConnectionConfig) -> URL:
        return URL.create(
            drivername="sqlite",
            database=connection_config.database,
        )

