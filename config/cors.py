"""应用运行时参数：名称、环境、调试、监听端口等（前缀 ``APP_``）。"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

from config import BASE_DIR


class CorsSettings(BaseSettings):
    """应用配置。"""
    model_config = SettingsConfigDict(
        env_file=BASE_DIR.joinpath(".env"),
        env_file_encoding="utf-8",
        env_prefix="CORS_",
        extra="ignore",
    )

    # 允许的域名
    allow_origins: List[str] = ["*"]

    # 允许的方法
    allow_methods: List[str] = ["*"]

    # 允许的头
    allow_headers: List[str] = ["*"]

    # 是否允许携带 cookie
    allow_credentials: bool = True

    # 用“正则表达式”来匹配允许的跨域来源
    allowed_origins_patterns: List[str] = []

    # 允许被前端读取
    exposed_headers: List[str] = []

    # 预检缓存时间
    max_age: int = 600