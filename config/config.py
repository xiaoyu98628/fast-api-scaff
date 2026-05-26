
from pydantic import BaseModel

from config.app import AppConfig
from config.cors import CorsConfig
from config.database import DatabaseConfig
from config.logging import LoggingConfig


class Config(BaseModel):

    app: AppConfig
    database: DatabaseConfig
    logging: LoggingConfig
    cors: CorsConfig


def config() -> Config:
    """获取配置。"""
    return Config(
        app=AppConfig(),
        database=DatabaseConfig(),
        logging=LoggingConfig(),
        cors=CorsConfig(),
    )
