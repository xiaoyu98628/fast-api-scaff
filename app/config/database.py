from typing import Annotated

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config.base import BASE_SETTINGS_CONFIG

type DatabaseTablePrefix = Annotated[
    str,
    Field(pattern=r"^(?:[a-z][a-z0-9_]*_)?$"),
]


class DatabaseSettings(BaseSettings):
    """应用启动时读取的数据库原始配置快照。"""

    model_config = SettingsConfigDict(
        **BASE_SETTINGS_CONFIG,
        env_prefix="DB_",
        env_nested_delimiter="__",
        frozen=True,
    )

    default: str | None = None
    connections: dict[str, dict[str, object]] = Field(default_factory=dict)
