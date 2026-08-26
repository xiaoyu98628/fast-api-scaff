from sqlalchemy import URL

from app.config.database import PostgreSQLDatabaseSettings
from app.infrastructure.database.connections.spec import DatabaseEngineSpec
from app.infrastructure.database.contracts.provider import DatabaseResourceDefinition


class PostgreSQLDatabaseProvider:
    drivers = ("postgresql", "pgsql")

    def prepare(self, raw_config: dict[str, object]) -> DatabaseResourceDefinition:
        settings = PostgreSQLDatabaseSettings.model_validate(raw_config)
        return DatabaseResourceDefinition(
            engine_spec=DatabaseEngineSpec(
                url=URL.create(
                    drivername="postgresql+asyncpg",
                    username=settings.username,
                    password=settings.password.get_secret_value(),
                    host=settings.host,
                    port=settings.port,
                    database=settings.database,
                ),
                options={
                    "echo": settings.echo,
                    "pool_size": settings.pool_size,
                    "max_overflow": settings.max_overflow,
                    "pool_pre_ping": settings.pool_pre_ping,
                    "pool_recycle": settings.pool_recycle,
                },
            ),
        )
