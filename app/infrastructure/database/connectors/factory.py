from app.infrastructure.database.connection import Connection
from app.infrastructure.database.connectors.connector import BaseConnector
from app.infrastructure.database.connectors.mysql import MysqlConnector
from app.infrastructure.database.connectors.postgresql import PostgresqlConnector
from app.infrastructure.database.connectors.sqlite import SqliteConnector
from config.database import DatabaseConfig


class ConnectionFactory:
    """连接工厂：按 driver 选择 Connector，创建 Connection 实例。"""

    def create_connector(self, driver: str) -> BaseConnector:
        match driver:
            case "mysql":
                return MysqlConnector()
            case "sqlite":
                return SqliteConnector()
            case "pgsql" | "postgresql":
                return PostgresqlConnector()
            case _:
                raise ValueError(f"Unsupported driver [{driver}].")

    def make(self, name: str, database_config: DatabaseConfig) -> Connection:
        connection_config = database_config.configuration(name)
        engine = self.create_connector(connection_config.driver).connect(
            connection_config,
            database_config=database_config,
        )
        return Connection(name=name, driver=connection_config.driver, engine=engine)
