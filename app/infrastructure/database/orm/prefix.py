from pydantic import TypeAdapter, ValidationError

from app.config.database import DatabaseSettings, DatabaseTablePrefix
from app.infrastructure.database.errors import DatabaseConfigurationError

DATABASE_TABLE_PREFIX_ADAPTER = TypeAdapter(DatabaseTablePrefix)


def resolve_database_table_prefix(
    settings: DatabaseSettings,
    name: str,
) -> str:
    """读取并校验指定连接的表前缀，不校验其余连接配置。"""
    raw_config = settings.connections.get(name)

    if raw_config is None:
        return ""

    try:
        return DATABASE_TABLE_PREFIX_ADAPTER.validate_python(raw_config.get("table_prefix", ""))
    except ValidationError:
        raise DatabaseConfigurationError(f"数据库连接 {name!r} 的表前缀配置不合法") from None
