"""日志 env 配置 + channels 声明（对齐 Laravel ``config/logging.php``）。"""

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from config.settings import BASE_SETTINGS_CONFIG

_VALID_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
_VALID_DRIVERS = frozenset({"single", "daily", "rotating"})


class LoggingConfig(BaseSettings):
    """``LOG_`` 前缀；通道装配见 ``infrastructure/logging/manager``。"""

    model_config = SettingsConfigDict(
        **BASE_SETTINGS_CONFIG,
        env_prefix="LOG_",
    )

    level: str | None = Field(default=None)
    driver: str = Field(default="single")
    json_enabled: bool = Field(default=False, validation_alias=AliasChoices("JSON", "JSON_ENABLED"))
    console_enabled: bool = Field(default=True, validation_alias=AliasChoices("CONSOLE_ENABLED", "CONSOLE"))
    request_body_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("REQUEST_BODY", "REQUEST_BODY_ENABLED"),
    )
    dir: str = Field(default="storage/logs", validation_alias=AliasChoices("DIR", "DIRECTORY"))
    max_bytes: int = Field(default=10 * 1024 * 1024)
    backup_count: int = Field(default=5)

    @field_validator("level")
    @classmethod
    def validate_level(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        upper = value.upper()
        if upper not in _VALID_LEVELS:
            raise ValueError(f"LOG_LEVEL 必须为 {_VALID_LEVELS} 之一")
        return upper

    @field_validator("driver")
    @classmethod
    def validate_driver(cls, value: str) -> str:
        lowered = value.lower()
        if lowered not in _VALID_DRIVERS:
            raise ValueError("LOG_DRIVER 必须为 single | daily | rotating")
        return lowered


LOG_CHANNELS: dict[str, dict[str, str | None | bool] | dict[str, str] | dict[str, str | list[str]]] = {
    "app": {
        "logger": "app",
        "path": "app.log",
        "level": None,
        "console": True,
    },
    "request": {
        "logger": "app.request",
        "path": "request.log",
        "level": "INFO",
    },
    "db": {
        "logger": "sqlalchemy.engine",
        "path": "db.log",
        "level": "INFO",
        "also": ["sqlalchemy.pool"],
    },
    "exception": {
        "logger": "app.channel.exception",
        "path": "exception.log",
        "level": "WARNING",
    },
}

