from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator
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
    version: str = "3.0.0"
    env: str = "local"
    debug: bool = False
    timezone: str = "UTC"
    service_code: str = Field(default="001", pattern=r"^\d{3}$")

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, timezone: str) -> str:
        try:
            ZoneInfo(timezone)
        except (ValueError, ZoneInfoNotFoundError) as error:
            raise ValueError("应用时区必须是有效的 IANA 时区") from error

        return timezone
