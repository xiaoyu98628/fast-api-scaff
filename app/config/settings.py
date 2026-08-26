from functools import lru_cache

from pydantic import BaseModel, ConfigDict

from app.config.app import AppSettings
from app.config.cache import CacheSettings
from app.config.cors import CorsSettings
from app.config.database import DatabaseSettings
from app.config.logging import LoggingSettings


class Settings(BaseModel):
    """应用完整配置。"""

    model_config = ConfigDict(frozen=True)

    app: AppSettings
    database: DatabaseSettings
    cache: CacheSettings
    cors: CorsSettings
    logging: LoggingSettings = LoggingSettings(_env_file=None)


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    """加载并缓存应用配置。"""
    return Settings(
        app=AppSettings(),
        database=DatabaseSettings(),
        cache=CacheSettings(),
        cors=CorsSettings(),
        logging=LoggingSettings(),
    )
