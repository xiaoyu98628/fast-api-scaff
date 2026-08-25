from pydantic import TypeAdapter, ValidationError

from app.config.database import DatabaseSettings, DatabaseTablePrefix
from app.infrastructure.database.contracts.provider import DatabaseResourceDefinition
from app.infrastructure.database.errors import DatabaseConfigurationError
from app.infrastructure.database.providers.registry import DEFAULT_DATABASE_PROVIDERS, DatabaseProviderRegistry

DATABASE_TABLE_PREFIX_ADAPTER = TypeAdapter(DatabaseTablePrefix)


def validate_database_definition(
    name: str,
    raw_config: dict[str, object],
    providers: DatabaseProviderRegistry = DEFAULT_DATABASE_PROVIDERS,
) -> DatabaseResourceDefinition:
    """通过 Provider 延迟校验一个数据库连接的原始配置。"""
    try:
        return providers.prepare(raw_config)
    except (ValidationError, DatabaseConfigurationError) as error:
        raise DatabaseConfigurationError(f"数据库连接 {name!r} 配置不合法") from error


def resolve_database_definition(
    settings: DatabaseSettings,
    name: str | None = None,
    providers: DatabaseProviderRegistry = DEFAULT_DATABASE_PROVIDERS,
) -> DatabaseResourceDefinition:
    """解析并校验默认或指定的数据库连接配置。"""
    resolved_name = name if name is not None else settings.default

    if resolved_name is None:
        raise DatabaseConfigurationError("默认数据库连接未配置")

    raw_config = settings.connections.get(resolved_name)

    if raw_config is None:
        raise DatabaseConfigurationError(f"数据库连接 {resolved_name!r} 未配置")

    return validate_database_definition(resolved_name, raw_config, providers)


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
