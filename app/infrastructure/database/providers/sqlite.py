from sqlalchemy import URL

from app.config.database import SQLiteDatabaseSettings
from app.infrastructure.database.connections.spec import DatabaseEngineSpec
from app.infrastructure.database.contracts.provider import DatabaseResourceDefinition


class SQLiteDatabaseProvider:
    drivers = ("sqlite",)

    def prepare(self, raw_config: dict[str, object]) -> DatabaseResourceDefinition:
        settings = SQLiteDatabaseSettings.model_validate(raw_config)
        return DatabaseResourceDefinition(
            engine_spec=DatabaseEngineSpec(
                url=URL.create(
                    drivername="sqlite+aiosqlite",
                    database=settings.resolved_database,
                ),
                options={"echo": settings.echo},
            ),
        )
