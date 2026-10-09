"""解析命名数据库连接并交给对应 Provider 严格校验。"""

from copy import deepcopy

from pydantic import ValidationError

from app.config.database import DatabaseSettings
from app.infrastructure.database.contracts.provider import DatabaseResourceDefinition
from app.infrastructure.database.errors import DatabaseConfigurationError
from app.infrastructure.database.providers.registry import DEFAULT_DATABASE_PROVIDERS, DatabaseProviderRegistry


def apply_database_connection_defaults(
    raw_config: dict[str, object],
    connection_defaults: dict[str, dict[str, object]],
) -> dict[str, object]:
    """按驱动合并公共默认值，并让命名连接的显式字段优先。"""

    driver = raw_config.get("driver")
    defaults = connection_defaults.get(driver, {}) if isinstance(driver, str) else {}
    return deepcopy(defaults) | deepcopy(raw_config)


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

    resolved_config = apply_database_connection_defaults(raw_config, settings.connection_defaults)
    return validate_database_definition(resolved_name, resolved_config, providers)
