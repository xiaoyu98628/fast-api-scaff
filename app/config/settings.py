from functools import lru_cache

from pydantic import BaseModel, ConfigDict

from app.config.app import AppSettings
from app.config.database import DatabaseSettings


class Settings(BaseModel):
    """应用完整配置。"""

    model_config = ConfigDict(frozen=True)

    app: AppSettings
    database: DatabaseSettings


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    """加载并缓存应用配置。"""
    return Settings(
        app=AppSettings(),
        database=DatabaseSettings(),
    )
