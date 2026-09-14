"""定义认证与会话生命周期配置。"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config.base import BASE_SETTINGS_CONFIG


class AuthSettings(BaseSettings):
    """应用启动时读取的认证配置快照。"""

    model_config = SettingsConfigDict(**BASE_SETTINGS_CONFIG, env_prefix="AUTH_", frozen=True)

    # 限制在 30 天内，避免误配置形成近似永久的服务端会话。
    session_ttl_seconds: int = Field(default=3600, gt=0, le=2_592_000)

    login_limit_cache: str | None = Field(default=None, min_length=1)
    login_max_failures: int = Field(default=5, ge=1, le=100)
    login_failure_window_seconds: int = Field(default=300, gt=0, le=86_400)
    login_lock_seconds: int = Field(default=900, gt=0, le=2_592_000)
