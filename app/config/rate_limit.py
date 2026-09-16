"""定义 HTTP 请求限流配置。"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config.base import BASE_SETTINGS_CONFIG


class RateLimitSettings(BaseSettings):
    """保存每个 IP 的共享配额与限流存储故障策略。"""

    model_config = SettingsConfigDict(**BASE_SETTINGS_CONFIG, env_prefix="RATE_LIMIT_", frozen=True)

    enabled: bool = False
    cache: str | None = Field(default=None, min_length=1)
    max_requests: int = Field(default=1000, ge=1, le=1_000_000)
    window_seconds: int = Field(default=60, ge=1, le=86_400)
    fail_open: bool = False
