"""定义认证与会话生命周期配置。"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config.base import BASE_SETTINGS_CONFIG


class AuthSettings(BaseSettings):
    """应用启动时读取的认证配置快照。"""

    model_config = SettingsConfigDict(**BASE_SETTINGS_CONFIG, env_prefix="AUTH_", frozen=True)

    # 限制在 30 天内，避免误配置形成近似永久的服务端会话。
    session_ttl_seconds: int = Field(default=3600, gt=0, le=2_592_000)
