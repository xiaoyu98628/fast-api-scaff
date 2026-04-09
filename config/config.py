"""组合子配置并提供进程内缓存的 ``get_config()``（单例式读取）。"""

from functools import lru_cache

from pydantic import BaseModel

from config.app import AppSettings
from config.database import DatabaseSettings
from config.logging import LoggingSettings
from config.redis import RedisSettings
from config.service import ServiceSettings


class Config(BaseModel):
    """聚合应用、数据库、Redis 等子配置；新增模块时在此加字段。"""
    app: AppSettings
    database: DatabaseSettings
    logging: LoggingSettings
    redis: RedisSettings
    service: ServiceSettings


@lru_cache
def get_config() -> Config:
    """返回缓存的 ``Config``；测试环境可通过 ``get_config.cache_clear()`` 刷新。"""
    return Config(
        app=AppSettings(),
        database=DatabaseSettings(),
        logging=LoggingSettings(),
        redis=RedisSettings(),
        service=ServiceSettings(),
    )