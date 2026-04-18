from functools import lru_cache

from pydantic import BaseModel

from config.app import AppSettings
from config.cors import CorsSettings
from config.database import DatabaseSettings
from config.jwt import JwtSettings
from config.logging import LoggingSettings
from config.redis import RedisSettings
from config.service import ServiceSettings


class Config(BaseModel):
    """主配置类，组合了所有子模块配置。"""

    app: AppSettings
    database: DatabaseSettings
    redis: RedisSettings
    jwt: JwtSettings
    cors: CorsSettings
    logging: LoggingSettings
    service: ServiceSettings


@lru_cache
def get_config() -> Config:
    """获取配置。"""
    return Config(
        app=AppSettings(),
        database=DatabaseSettings(),
        redis=RedisSettings(),
        jwt=JwtSettings(),
        cors=CorsSettings(),
        logging=LoggingSettings(),
        service=ServiceSettings(),
    )
