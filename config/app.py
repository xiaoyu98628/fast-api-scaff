"""应用运行时参数：名称、环境、调试、监听端口等（前缀 ``APP_``）。"""

from pydantic_settings import BaseSettings, SettingsConfigDict

from config import BASE_DIR


class AppSettings(BaseSettings):
    """应用配置。"""
    model_config = SettingsConfigDict(
        env_file=BASE_DIR.joinpath(".env"),
        env_file_encoding="utf-8",
        env_prefix="APP_",
        extra="ignore",
    )

    name: str = "FastAPI scaff"
    env: str = "dev"
    debug: bool = True
    port: int = 8000