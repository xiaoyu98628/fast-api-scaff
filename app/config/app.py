from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config.base import BASE_SETTINGS_CONFIG


class AppSettings(BaseSettings):
    """应用启动配置。"""

    model_config = SettingsConfigDict(
        **BASE_SETTINGS_CONFIG,
        env_prefix="APP_",
        frozen=True,
    )

    name: str = "fast-api-scaff"
    version: str = "3.0.3"
    env: str = "local"
    debug: bool = False
    service_code: str = Field(default="001", pattern=r"^\d{3}$")
