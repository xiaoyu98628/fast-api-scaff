"""跨域配置（前缀 ``CORS_``）。"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from config.settings import BASE_SETTINGS_CONFIG


class CorsConfig(BaseSettings):
    """CORS 相关环境变量。"""

    model_config = SettingsConfigDict(
        **BASE_SETTINGS_CONFIG,
        env_prefix="CORS_",
    )

    allow_origins: list[str] = Field(default_factory=lambda: ["*"])
    allow_methods: list[str] = Field(default_factory=lambda: ["*"])
    allow_headers: list[str] = Field(default_factory=lambda: ["*"])
    allow_credentials: bool = True
    allowed_origins_patterns: list[str] = Field(default_factory=list)
    exposed_headers: list[str] = Field(default_factory=list)
    max_age: int = 600
