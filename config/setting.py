"""组合子配置并提供进程内缓存的 ``get_setting()``（单例式读取）。"""

from functools import lru_cache

from pydantic import BaseModel

from config.app import AppSettings
from config.cors import CorsSettings
from config.database import DatabaseSettings
from config.jwt import JwtSettings
from config.logging import LoggingSettings
from config.redis import RedisSettings
from config.service import ServiceSettings

class Settings(BaseModel):
    """聚合应用、数据库、Redis 等子配置；新增模块时在此加字段。"""

    app: AppSettings
    database: DatabaseSettings
    jwt: JwtSettings
    logging: LoggingSettings
    redis: RedisSettings
    service: ServiceSettings
    cors: CorsSettings

@lru_cache
def settings() -> Settings:
    """返回缓存的 ``Setting``；测试环境可通过 ``get_setting.cache_clear()`` 刷新。"""

    return Settings(
        app=AppSettings(),
        database=DatabaseSettings(),
        jwt=JwtSettings(),
        logging=LoggingSettings(),
        redis=RedisSettings(),
        service=ServiceSettings(),
        cors=CorsSettings(),
    )