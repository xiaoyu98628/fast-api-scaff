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

    # 允许发起跨域请求的来源，对应响应头 Access-Control-Allow-Origin。
    allow_origins: list[str] = Field(default_factory=lambda: ["*"])

    # 允许跨域请求使用的 HTTP 方法，对应响应头 Access-Control-Allow-Methods。
    allow_methods: list[str] = Field(default_factory=lambda: ["*"])

    # 允许浏览器在跨域请求中发送的请求头，对应响应头 Access-Control-Allow-Headers。
    allow_headers: list[str] = Field(default_factory=lambda: ["*"])

    # 是否允许跨域请求携带 Cookie、HTTP 认证等凭证。
    allow_credentials: bool = False

    # 允许浏览器 JavaScript 读取的响应头，对应响应头 Access-Control-Expose-Headers。
    expose_headers: list[str] = Field(default_factory=lambda: ["*"])

    # 浏览器缓存 CORS 预检结果的秒数，对应响应头 Access-Control-Max-Age。
    max_age: int = Field(default=600, ge=0)

    @model_validator(mode="after")
    def validate_credential_origins(self) -> Self:
        if self.allow_credentials and "*" in self.allow_origins:
            message = "CORS_ALLOW_ORIGINS cannot contain '*' when CORS_ALLOW_CREDENTIALS is true"
            raise ValueError(message)

        return self
