"""维护数据库 driver 到 Provider 的显式映射。"""

from collections.abc import Iterable

from app.infrastructure.database.contracts.provider import DatabaseProvider, DatabaseResourceDefinition
from app.infrastructure.database.errors import DatabaseConfigurationError
from app.infrastructure.database.providers.mysql import MySQLDatabaseProvider
from app.infrastructure.database.providers.postgresql import PostgreSQLDatabaseProvider
from app.infrastructure.database.providers.sqlite import SQLiteDatabaseProvider


class DatabaseProviderRegistry:
    """显式注册并按 driver 查找数据库 Provider。"""

    def __init__(self, providers: Iterable[DatabaseProvider]) -> None:
        """注册 Provider，并拒绝空名称或重复的 driver。"""

        self._registered = tuple(providers)
        self._providers: dict[str, DatabaseProvider] = {}

        # 构建时拒绝空名称和重复注册，使运行期选择保持确定性。
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
        """返回当前注册的全部 driver 名称。"""

        return tuple(self._providers)

    def prepare(self, raw_config: dict[str, object]) -> DatabaseResourceDefinition:
        """按原始配置中的 driver 选择 Provider 并完成严格校验。"""

        driver = raw_config.get("driver")
        if not isinstance(driver, str) or not driver:
            raise DatabaseConfigurationError("数据库连接没有配置有效的 driver")

        provider = self._providers.get(driver)
        if provider is None:
            raise DatabaseConfigurationError(f"不支持数据库驱动 {driver!r}")

        return provider.prepare(raw_config)

    def extended(self, *providers: DatabaseProvider) -> DatabaseProviderRegistry:
        """返回包含额外 Provider 的新注册表，不修改默认实例。"""

        return DatabaseProviderRegistry((*self._registered, *providers))


DEFAULT_DATABASE_PROVIDERS = DatabaseProviderRegistry(
    (
        MySQLDatabaseProvider(),
        PostgreSQLDatabaseProvider(),
        SQLiteDatabaseProvider(),
    )
)
