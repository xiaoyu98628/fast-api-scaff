"""把 SQLite 配置转换为 aiosqlite SQLAlchemy Engine 规格。"""

from sqlalchemy import URL

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
        )
