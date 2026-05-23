from app.infrastructure.database.connectors.connector import BaseConnector
from config.database import DatabaseConfig, DbDriver


class SqliteConnector(BaseConnector):
    driver = DbDriver.SQLITE

    def engine_options(self, database_config: DatabaseConfig) -> dict:
        return {"echo": database_config.echo}
