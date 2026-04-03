from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "FastAPI Scaff"
    app_env: str = "dev"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"
    host: str = "127.0.0.1"
    port: int = 8000

    database_url: str = "mysql+aiomysql:///./fast_api_scaff"
    sqlalchemy_echo: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
