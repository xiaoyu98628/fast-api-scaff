from app.infrastructure.database.connection import Connection
from app.infrastructure.database.connectors.factory import ConnectionFactory
from config.config import config
from config.database import DatabaseConfig


def resolve_connection_name(name: str | None, *, default: str) -> str:
    return default if name is None else name


class DatabaseManager:
    """数据库管理器：按连接名解析、缓存并返回 Connection。"""

    def __init__(self, database_config: DatabaseConfig) -> None:
        self._config = database_config
        self._factory = ConnectionFactory()
        self._connections: dict[str, Connection] = {}

    @property
    def default_connection(self) -> str:
        return self._config.connection

    def connection(self, name: str | None = None) -> Connection:
        resolved = resolve_connection_name(name, default=self.default_connection)
        if resolved not in self._connections:
            self._connections[resolved] = self._factory.make(resolved, self._config)
        return self._connections[resolved]

    async def disconnect(self) -> None:
        for connection in self._connections.values():
            await connection.disconnect()
        self._connections.clear()


_manager: DatabaseManager | None = None


def get_manager() -> DatabaseManager:
    global _manager
    if _manager is None:
        _manager = DatabaseManager(config().database)
    return _manager
