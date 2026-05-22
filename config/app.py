
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from paths import ENV_FILE


class AppConfig(BaseSettings):

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        env_prefix="APP_",
        extra="ignore",
    )

    name: str = Field(default="FastAPI scaff", description="应用名称")
    env: str = Field(default="dev", description="环境")
    debug: bool = Field(default=True, description="调试模式")
    port: int = Field(default=8000, description="端口")
