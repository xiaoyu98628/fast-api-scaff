"""定义应用身份、运行环境和响应服务编码配置。"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config.base import BASE_SETTINGS_CONFIG


class AppSettings(BaseSettings):
    """应用启动配置。"""

    model_config = SettingsConfigDict(
        **BASE_SETTINGS_CONFIG,
        env_prefix="APP_",
        frozen=True,
    )

    name: str = "fast-api-scaff"
    version: str = "1.0.0"
    env: str = "local"
    debug: bool = False
    # 统一响应码会把三位服务编码作为前缀，固定长度可避免跨服务冲突。
    service_code: str = Field(default="001", pattern=r"^\d{3}$")
