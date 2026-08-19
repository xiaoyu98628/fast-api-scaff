from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config.base import BASE_SETTINGS_CONFIG


class CorsSettings(BaseSettings):
    """HTTP CORS 配置。"""

    model_config = SettingsConfigDict(
        **BASE_SETTINGS_CONFIG,
        env_prefix="CORS_",
        frozen=True,
    )

    enabled: bool = True
    allow_origins: list[str] = Field(default_factory=lambda: ["*"])
    allow_methods: list[str] = Field(default_factory=lambda: ["*"])
    allow_headers: list[str] = Field(default_factory=lambda: ["*"])
    allow_credentials: bool = False
    expose_headers: list[str] = Field(default_factory=list)
    max_age: int = Field(default=600, ge=0)

    @model_validator(mode="after")
    def validate_credential_origins(self) -> Self:
        if self.allow_credentials and "*" in self.allow_origins:
            message = "CORS_ALLOW_ORIGINS cannot contain '*' when CORS_ALLOW_CREDENTIALS is true"
            raise ValueError(message)

        return self
