from pydantic_settings import BaseSettings, SettingsConfigDict

from config import BASE_DIR

class AppSettings(BaseSettings):
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