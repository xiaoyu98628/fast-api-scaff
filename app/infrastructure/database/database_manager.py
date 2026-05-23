from app.infrastructure.database.connection import Connection
from app.infrastructure.database.connectors.connection_factory import ConnectionFactory
from config.config import config
from config.database import DatabaseConfig, DbDriver


class DatabaseManager:
    """数据库管理器（对应 Laravel Database\\DatabaseManager）。"""

    def __init__(self, database_config: DatabaseConfig) -> None:
        self._config = database_config
        self._factory = ConnectionFactory()
        self._connections: dict[str, Connection] = {}

    def get_default_connection(self) -> str:
        return self._config.connection.value

    def _resolve_name(self, name: DbDriver | str | None) -> str:
        if name is None:
            return self.get_default_connection()
        return name.value if isinstance(name, DbDriver) else name

    def connection(self, name: DbDriver | str | None = None) -> Connection:
        resolved = self._resolve_name(name)
        if resolved not in self._connections:
            driver = DbDriver(resolved)
            self._connections[resolved] = self._factory.make(driver, self._config, resolved)
        return self._connections[resolved]

    async def disconnect(self) -> None:
        for connection in self._connections.values():
            await connection.disconnect()
        self._connections.clear()


_manager: DatabaseManager | None = None


def get_database_manager() -> DatabaseManager:
    global _manager
    if _manager is None:
        _manager = DatabaseManager(config().database)
    return _manager
