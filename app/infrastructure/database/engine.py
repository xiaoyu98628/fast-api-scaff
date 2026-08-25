from app.config.database import (
    DatabaseConnectionSettings,
    MySQLConnectionSettings,
    PostgreSQLConnectionSettings,
    SQLiteConnectionSettings,
)
from app.infrastructure.database.backends.mysql import build_mysql_engine_spec
from app.infrastructure.database.backends.postgresql import build_postgresql_engine_spec
from app.infrastructure.database.backends.spec import DatabaseEngineSpec
from app.infrastructure.database.backends.sqlite import build_sqlite_engine_spec


def build_database_engine_spec(settings: DatabaseConnectionSettings) -> DatabaseEngineSpec:
    """根据数据库连接类型分派对应的 Engine 配置构建器。"""
    match settings:
        case MySQLConnectionSettings():
            return build_mysql_engine_spec(settings)
        case PostgreSQLConnectionSettings():
            return build_postgresql_engine_spec(settings)
        case SQLiteConnectionSettings():
            return build_sqlite_engine_spec(settings)

    raise TypeError(f"不支持的数据库连接配置: {type(settings).__name__}")
