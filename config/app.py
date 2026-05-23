
from pydantic import Field
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
