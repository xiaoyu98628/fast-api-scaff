from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config.base import BASE_SETTINGS_CONFIG

type LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


def _default_handlers() -> dict[str, dict[str, object]]:
    return {
        "stdout": {
            "driver": "stream",
            "stream": "stdout",
        }
    }


class LoggingSettings(BaseSettings):
    """应用日志原始配置快照。"""

    model_config = SettingsConfigDict(
        **BASE_SETTINGS_CONFIG,
        env_prefix="LOG_",
        env_nested_delimiter="__",
        frozen=True,
    )

    level: LogLevel = "INFO"
    access_enabled: bool = True
    active_handlers: tuple[str, ...] = ("stdout",)
    handlers: dict[str, dict[str, object]] = Field(default_factory=_default_handlers)
