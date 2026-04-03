from functools import lru_cache

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

from config import BASE_DIR


class Settings(BaseSettings):
    """应用配置。"""
    model_config = SettingsConfigDict(
        env_file=BASE_DIR.joinpath(".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "FastAPI Scaff"
    app_env: str = "dev"
    app_debug: bool = True
    app_host: str = "127.0.0.1"
    app_port: int = 8000

    database_url: str = "mysql+aiomysql:///./fast_api_scaff"
    sqlalchemy_echo: bool = False

    @property
    def base_path(self) -> Path:
        return Path(__file__).resolve().parent.parent

@lru_cache
def get_settings() -> Settings:
    return Settings()
