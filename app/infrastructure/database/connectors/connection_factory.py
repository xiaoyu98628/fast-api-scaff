from app.infrastructure.database.connection import Connection
from app.infrastructure.database.connectors.connector import Connector
from app.infrastructure.database.connectors.mysql_connector import MysqlConnector
from app.infrastructure.database.connectors.postgresql_connector import PostgresqlConnector
from app.infrastructure.database.connectors.sqlite_connector import SqliteConnector
from config.database import DatabaseConfig, DbDriver


class ConnectionFactory:
    """连接工厂（对应 Laravel Connectors\\ConnectionFactory）。"""

    def create_connector(self, driver: DbDriver) -> Connector:
        match driver:
            case DbDriver.MYSQL:
                return MysqlConnector()
            case DbDriver.SQLITE:
                return SqliteConnector()
            case DbDriver.POSTGRESQL:
                return PostgresqlConnector()

    def make(self, driver: DbDriver, database_config: DatabaseConfig, name: str) -> Connection:
        connector = self.create_connector(driver)
        engine = connector.connect(database_config)
        return Connection(name=name, driver=driver, engine=engine)
