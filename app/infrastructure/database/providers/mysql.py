"""把 MySQL 配置转换为 asyncmy SQLAlchemy Engine 规格。"""

from sqlalchemy import URL

from app.config.database import MySQLDatabaseSettings
from app.infrastructure.database.connections.spec import DatabaseEngineSpec
from app.infrastructure.database.contracts.provider import DatabaseResourceDefinition


class MySQLDatabaseProvider:
    """校验 MySQL 配置并组装连接池与字符集参数。"""

    drivers = ("mysql",)

    def prepare(self, raw_config: dict[str, object]) -> DatabaseResourceDefinition:
        """生成不会立即建立网络连接的数据库资源定义。"""

        settings = MySQLDatabaseSettings.model_validate(raw_config)
        return DatabaseResourceDefinition(
            engine_spec=DatabaseEngineSpec(
                url=URL.create(
                    drivername="mysql+asyncmy",
                    username=settings.username,
                    password=settings.password.get_secret_value(),
                    host=settings.host,
                    port=settings.port,
                    database=settings.database,
                    query={"charset": settings.charset},
                ),
                options={
                    "pool_size": settings.pool_size,
                    "max_overflow": settings.max_overflow,
                    "pool_pre_ping": settings.pool_pre_ping,
                    "pool_recycle": settings.pool_recycle,
                },
                log_queries=settings.echo,
                slow_query_ms=settings.slow_query_ms,
            ),
        )
