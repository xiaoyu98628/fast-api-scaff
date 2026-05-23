
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from config.settings import BASE_SETTINGS_CONFIG


class AppConfig(BaseSettings):

    model_config = SettingsConfigDict(
        **BASE_SETTINGS_CONFIG,
        env_prefix="APP_",
    )

    name: str = Field(default="FastAPI scaff", description="应用名称")
    env: str = Field(default="dev", description="环境")
    debug: bool = Field(default=True, description="调试模式")
    port: int = Field(default=8000, description="端口")

    service_code: str = Field(default="001", description="三位服务码，如 001、002、010。")

    @field_validator("service_code")
    @classmethod
    def validate_service_code(cls, value: str) -> str:
        if not value.isdigit() or len(value) != 3:
            raise ValueError("SERVICE_CODE 必须为三位数字（如 001）")
        return value
