"""聚合各子系统配置并提供进程级加载入口。"""

from functools import lru_cache

from pydantic import BaseModel, ConfigDict, Field

from app.config.app import AppSettings
from app.config.auth import AuthSettings
from app.config.cache import CacheSettings
from app.config.cors import CorsSettings
from app.config.database import DatabaseSettings
from app.config.http import HttpSettings
from app.config.logging import LoggingSettings
from app.config.queue import QueueSettings


class Settings(BaseModel):
    """应用完整配置。"""

    model_config = ConfigDict(frozen=True)

    queue: QueueSettings = Field(default_factory=lambda: QueueSettings(_env_file=None))
    app: AppSettings
    auth: AuthSettings = Field(default_factory=lambda: AuthSettings(_env_file=None))
    database: DatabaseSettings
    cache: CacheSettings
    http: HttpSettings = Field(default_factory=lambda: HttpSettings(_env_file=None))
    cors: CorsSettings
    logging: LoggingSettings = Field(default_factory=lambda: LoggingSettings(_env_file=None))


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    """加载并缓存应用配置。"""

    # 同一进程内复用不可变快照，避免不同宿主组件读取到不一致的环境状态。
    return Settings(
        queue=QueueSettings(),
        app=AppSettings(),
        auth=AuthSettings(),
        database=DatabaseSettings(),
        cache=CacheSettings(),
        http=HttpSettings(),
        cors=CorsSettings(),
        logging=LoggingSettings(),
    )
