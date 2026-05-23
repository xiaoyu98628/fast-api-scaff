from app.infrastructure.database.connection import Connection
from app.infrastructure.database.connectors.connector import BaseConnector
from app.infrastructure.database.connectors.mysql import MysqlConnector
from app.infrastructure.database.connectors.postgresql import PostgresqlConnector
from app.infrastructure.database.connectors.sqlite import SqliteConnector
from config.database import DatabaseConfig, DbDriver


class ConnectionFactory:
    """连接工厂：按 driver 选择 Connector，创建 Connection 实例。"""

    def create_connector(self, driver: DbDriver) -> BaseConnector:
        match driver:
            case DbDriver.MYSQL:
                return MysqlConnector()
            case DbDriver.SQLITE:
                return SqliteConnector()
            case DbDriver.POSTGRESQL:
                return PostgresqlConnector()

    def make(self, name: str, database_config: DatabaseConfig) -> Connection:
        driver = DbDriver(name)
        engine = self.create_connector(driver).connect(database_config)
        return Connection(name=name, driver=driver, engine=engine)
