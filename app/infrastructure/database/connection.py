from pydantic import TypeAdapter, ValidationError

from app.config.database import DatabaseConnectionSettings, DatabaseSettings
from app.infrastructure.database.errors import DatabaseConfigurationError

DATABASE_CONNECTION_ADAPTER = TypeAdapter(DatabaseConnectionSettings)


def validate_database_connection(
    name: str,
    raw_config: dict[str, object],
) -> DatabaseConnectionSettings:
    """延迟校验一个数据库连接的原始配置。"""
    try:
        return DATABASE_CONNECTION_ADAPTER.validate_python(raw_config)
    except ValidationError:
        raise DatabaseConfigurationError(f"数据库连接 {name!r} 配置不合法") from None


def resolve_database_connection(
    settings: DatabaseSettings,
    name: str | None = None,
) -> DatabaseConnectionSettings:
    """解析并校验默认或指定的数据库连接配置。"""
    resolved_name = name if name is not None else settings.default

    if resolved_name is None:
        raise DatabaseConfigurationError("默认数据库连接未配置")

    raw_config = settings.connections.get(resolved_name)

    if raw_config is None:
        raise DatabaseConfigurationError(f"数据库连接 {resolved_name!r} 未配置")

    return validate_database_connection(resolved_name, raw_config)
