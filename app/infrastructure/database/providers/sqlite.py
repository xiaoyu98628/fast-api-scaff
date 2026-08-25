from pathlib import Path
from typing import Literal

from pydantic import Field
from sqlalchemy import URL

from app.infrastructure.database.contracts.provider import DatabaseResourceDefinition
from app.infrastructure.database.engine_spec import DatabaseEngineSpec
from app.infrastructure.database.providers.base import BaseDatabaseSettings
from app.runtime.paths import STORAGE_DIR


class SQLiteDatabaseSettings(BaseDatabaseSettings):
    driver: Literal["sqlite"]
    database: str = Field(min_length=1)

    @property
    def resolved_database(self) -> str:
        if self.database == ":memory:":
            return self.database

        database_path = Path(self.database)
        if database_path.is_absolute():
            return str(database_path)

        return str(STORAGE_DIR / database_path)


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
