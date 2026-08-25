from typing import Literal

from pydantic import Field, SecretStr
from sqlalchemy import URL

from app.infrastructure.database.contracts.provider import DatabaseResourceDefinition
from app.infrastructure.database.engine_spec import DatabaseEngineSpec
from app.infrastructure.database.providers.base import PooledDatabaseSettings


class MySQLDatabaseSettings(PooledDatabaseSettings):
    driver: Literal["mysql"]
    host: str = Field(min_length=1)
    port: int = Field(default=3306, ge=1, le=65535)
    database: str = Field(min_length=1)
    username: str = Field(min_length=1)
    password: SecretStr = Field(min_length=1)
    charset: str = Field(default="utf8mb4", min_length=1)


class MySQLDatabaseProvider:
    drivers = ("mysql",)

    def prepare(self, raw_config: dict[str, object]) -> DatabaseResourceDefinition:
        settings = MySQLDatabaseSettings.model_validate(raw_config)
        return DatabaseResourceDefinition(
            table_prefix=settings.table_prefix,
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
                    "echo": settings.echo,
                    "pool_size": settings.pool_size,
                    "max_overflow": settings.max_overflow,
                    "pool_pre_ping": settings.pool_pre_ping,
                    "pool_recycle": settings.pool_recycle,
                },
            ),
        )
