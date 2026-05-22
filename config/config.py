
from pydantic import BaseModel

from config.app import AppConfig
from config.database import DatabaseConfig


class Config(BaseModel):

    app: AppConfig
    database: DatabaseConfig


def config() -> Config:
    """获取配置。"""
    return Config(
        app=AppConfig(),
        database=DatabaseConfig(),
    )
