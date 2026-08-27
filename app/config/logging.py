from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config.base import BASE_SETTINGS_CONFIG

type LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
type LogFormat = Literal["json", "text"]


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
    format: LogFormat = "json"
    access_enabled: bool = True
    access_exclude_routes: frozenset[str] = Field(default_factory=lambda: frozenset({"/health"}))
    active_handlers: tuple[str, ...] = ("stdout",)
    handlers: dict[str, dict[str, object]] = Field(default_factory=_default_handlers)

    @field_validator("access_exclude_routes")
    @classmethod
    def validate_access_exclude_routes(cls, routes: frozenset[str]) -> frozenset[str]:
        if any(not route.startswith("/") for route in routes):
            raise ValueError("排除的 HTTP 路由必须以 '/' 开头")

        return routes
