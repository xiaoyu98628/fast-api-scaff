from pydantic import BaseModel
from functools import lru_cache

from config.app import AppSettings
from config.database import DatabaseSettings


class Config(BaseModel):
    """主配置类，组合了所有子模块配置"""
    app: AppSettings
    database: DatabaseSettings

@lru_cache
def get_config() -> Config:
    """获取配置"""
    return Config(
        app=AppSettings(),
        database=DatabaseSettings()
    )