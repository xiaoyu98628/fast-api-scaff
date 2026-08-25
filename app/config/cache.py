from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config.base import BASE_SETTINGS_CONFIG


class CacheSettings(BaseSettings):
    """应用启动时读取的缓存配置。"""

    model_config = SettingsConfigDict(
        **BASE_SETTINGS_CONFIG,
        env_prefix="CACHE_",
        env_nested_delimiter="__",
        frozen=True,
    )

    default: str | None = None
    namespace: str = ""
    default_ttl: int | None = Field(default=300, gt=0)
    connections: dict[str, dict[str, object]] = Field(default_factory=dict)
