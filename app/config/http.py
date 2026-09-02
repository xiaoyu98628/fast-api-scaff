from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config.base import BASE_SETTINGS_CONFIG


class HttpTimeoutSettings(BaseModel):
    """HTTP 请求阶段超时。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    connect: float = Field(default=3.0, gt=0)
    read: float = Field(default=10.0, gt=0)
    write: float = Field(default=10.0, gt=0)


class HttpPoolSettings(BaseModel):
    """一个 HTTP 连接池的容量和等待策略。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    timeout: float = Field(default=5.0, gt=0)
    max_connections: int = Field(default=100, ge=1)
    max_keepalive_connections: int = Field(default=20, ge=0)
    keepalive_expiry: float = Field(default=30.0, gt=0)

    @model_validator(mode="after")
    def validate_connections(self) -> HttpPoolSettings:
        if self.max_keepalive_connections > self.max_connections:
            raise ValueError("max_keepalive_connections 不能大于 max_connections")

        return self


class HttpSettings(BaseSettings):
    """不包含具体上游地址的全局 HTTP 出站配置。"""

    model_config = SettingsConfigDict(
        **BASE_SETTINGS_CONFIG,
        env_prefix="HTTP_",
        env_nested_delimiter="__",
        frozen=True,
    )

    timeout: HttpTimeoutSettings = HttpTimeoutSettings()
    pool: HttpPoolSettings = HttpPoolSettings()
    stream_pool: HttpPoolSettings = HttpPoolSettings(
        timeout=10.0,
        max_connections=100,
        max_keepalive_connections=10,
    )
    pool_warning_ratio: float = Field(default=0.8, gt=0, le=1)
    max_response_bytes: int = Field(default=10 * 1024 * 1024, ge=1)
    verify: bool = True
    follow_redirects: bool = False
    trust_env: bool = False
