"""把 SQLite 配置转换为启用外键约束的 aiosqlite Engine 规格。"""

from sqlalchemy import URL, event
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import ConnectionPoolEntry

from app.config.database import SQLiteDatabaseSettings
from app.infrastructure.database.connections.spec import DatabaseEngineSpec
from app.infrastructure.database.contracts.provider import DatabaseResourceDefinition


class SQLiteDatabaseProvider:
    """解析内存库、绝对路径和 storage 相对路径。"""

    drivers = ("sqlite",)

    def prepare(self, raw_config: dict[str, object]) -> DatabaseResourceDefinition:
        """校验配置并生成不包含连接池参数的资源定义。"""

        settings = SQLiteDatabaseSettings.model_validate(raw_config)
        return DatabaseResourceDefinition(
            engine_spec=DatabaseEngineSpec(
                url=URL.create(
                    drivername="sqlite+aiosqlite",
                    database=settings.resolved_database,
                ),
                options={},
                log_queries=settings.echo,
                slow_query_ms=settings.slow_query_ms,
            ),
            configure_engine=_configure_sqlite_engine,
        )


def _configure_sqlite_engine(engine: AsyncEngine) -> None:
    """让该 Engine 建立的每个 SQLite 连接都执行外键约束。"""

    # SQLite 的外键开关属于连接级状态，必须覆盖连接池后续创建的每个连接。
    @event.listens_for(engine.sync_engine, "connect")
    def enable_foreign_keys(dbapi_connection: DBAPIConnection, _connection_record: ConnectionPoolEntry) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()
