from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config.base import BASE_SETTINGS_CONFIG


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(**BASE_SETTINGS_CONFIG, env_prefix="AUTH_", frozen=True)

    session_ttl_seconds: int = Field(default=3600, gt=0, le=2_592_000)
