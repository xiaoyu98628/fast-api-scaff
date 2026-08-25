from sqlalchemy import URL

from app.config.database import SQLiteDatabaseSettings
from app.infrastructure.database.contracts.provider import DatabaseResourceDefinition
from app.infrastructure.database.engine_spec import DatabaseEngineSpec


class SQLiteDatabaseProvider:
    drivers = ("sqlite",)

    def prepare(self, raw_config: dict[str, object]) -> DatabaseResourceDefinition:
        settings = SQLiteDatabaseSettings.model_validate(raw_config)
        return DatabaseResourceDefinition(
            table_prefix=settings.table_prefix,
            engine_spec=DatabaseEngineSpec(
                url=URL.create(
                    drivername="sqlite+aiosqlite",
                    database=settings.resolved_database,
                ),
                options={"echo": settings.echo},
            ),
        )
