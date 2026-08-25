from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config.base import BASE_SETTINGS_CONFIG
from app.runtime.paths import STORAGE_DIR

type DatabaseTablePrefix = Annotated[
    str,
    Field(pattern=r"^(?:[a-z][a-z0-9_]*_)?$"),
]


class DatabaseSettings(BaseSettings):
    """应用启动时读取的数据库原始配置快照。"""

    model_config = SettingsConfigDict(
        **BASE_SETTINGS_CONFIG,
        env_prefix="DB_",
        env_nested_delimiter="__",
        frozen=True,
    )

    default: str | None = None
    connections: dict[str, dict[str, object]] = Field(default_factory=dict)


class BaseDatabaseSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    echo: bool = False
    table_prefix: DatabaseTablePrefix = ""


class PooledDatabaseSettings(BaseDatabaseSettings):
    pool_size: int = Field(default=10, ge=1)
    max_overflow: int = Field(default=20, ge=0)
    pool_pre_ping: bool = True
    pool_recycle: int = Field(default=3600, ge=-1)


class MySQLDatabaseSettings(PooledDatabaseSettings):
    driver: Literal["mysql"]
    host: str = Field(min_length=1)
    port: int = Field(default=3306, ge=1, le=65535)
    database: str = Field(min_length=1)
    username: str = Field(min_length=1)
    password: SecretStr = Field(min_length=1)
    charset: str = Field(default="utf8mb4", min_length=1)


class PostgreSQLDatabaseSettings(PooledDatabaseSettings):
    driver: Literal["postgresql", "pgsql"]
    host: str = Field(min_length=1)
    port: int = Field(default=5432, ge=1, le=65535)
    database: str = Field(min_length=1)
    username: str = Field(min_length=1)
    password: SecretStr = Field(min_length=1)


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
