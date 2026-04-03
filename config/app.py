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

    name: str = "FastAPI Scaff"
    env: str = "dev"
    debug: bool = True
    host: str = "127.0.0.1"
    port: int = 8000