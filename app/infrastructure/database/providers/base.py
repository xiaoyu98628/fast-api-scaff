from pydantic import BaseModel, ConfigDict, Field

from app.config.database import DatabaseTablePrefix


class BaseDatabaseSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    echo: bool = False
    table_prefix: DatabaseTablePrefix = ""


class PooledDatabaseSettings(BaseDatabaseSettings):
    pool_size: int = Field(default=10, ge=1)
    max_overflow: int = Field(default=20, ge=0)
    pool_pre_ping: bool = True
    pool_recycle: int = Field(default=3600, ge=-1)
