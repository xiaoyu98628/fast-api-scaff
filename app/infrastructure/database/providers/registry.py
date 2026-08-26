from collections.abc import Iterable

from app.infrastructure.database.contracts.provider import DatabaseProvider, DatabaseResourceDefinition
from app.infrastructure.database.errors import DatabaseConfigurationError
from app.infrastructure.database.providers.mysql import MySQLDatabaseProvider
from app.infrastructure.database.providers.postgresql import PostgreSQLDatabaseProvider
from app.infrastructure.database.providers.sqlite import SQLiteDatabaseProvider


class DatabaseProviderRegistry:
    """显式注册并按 driver 查找数据库 Provider。"""

    def __init__(self, providers: Iterable[DatabaseProvider]) -> None:
        self._registered = tuple(providers)
        self._providers: dict[str, DatabaseProvider] = {}

        for provider in self._registered:
            if not provider.drivers:
                raise DatabaseConfigurationError("数据库 Provider 至少需要一个 driver")

            for driver in provider.drivers:
                if not driver:
                    raise DatabaseConfigurationError("数据库 Provider 的 driver 不能为空")

                if driver in self._providers:
                    raise DatabaseConfigurationError(f"数据库驱动 {driver!r} 重复注册")

                self._providers[driver] = provider

    @property
    def drivers(self) -> tuple[str, ...]:
        return tuple(self._providers)

    def prepare(self, raw_config: dict[str, object]) -> DatabaseResourceDefinition:
        driver = raw_config.get("driver")
        if not isinstance(driver, str) or not driver:
            raise DatabaseConfigurationError("数据库连接没有配置有效的 driver")

        provider = self._providers.get(driver)
        if provider is None:
            raise DatabaseConfigurationError(f"不支持数据库驱动 {driver!r}")

        return provider.prepare(raw_config)

    def extended(self, *providers: DatabaseProvider) -> DatabaseProviderRegistry:
        return DatabaseProviderRegistry((*self._registered, *providers))


DEFAULT_DATABASE_PROVIDERS = DatabaseProviderRegistry(
    (
        MySQLDatabaseProvider(),
        PostgreSQLDatabaseProvider(),
        SQLiteDatabaseProvider(),
    )
)
