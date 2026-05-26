import re
from pathlib import Path

from pydantic import AliasChoices, BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from config.settings import BASE_SETTINGS_CONFIG
from paths import BASE_DIR

_VALID_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


def _slugify_app_name(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "app"


class LogChannel(BaseModel):
    """单个日志通道（对齐 Laravel channels 思路，按用途分文件而非按级别拆文件）。"""

    logger: str
    filename: str
    level: str = "DEBUG"
    driver: str = "single"


class LoggingConfig(BaseSettings):
    """日志配置（``LOG_`` 前缀）；装配见 ``infrastructure/logging/setup``。"""

    model_config = SettingsConfigDict(
        **BASE_SETTINGS_CONFIG,
        env_prefix="LOG_",
    )

    level: str | None = Field(default=None, description="全局级别；为空时随 APP_DEBUG。")
    driver: str = Field(default="single", description="single | daily | rotating")
    json_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("JSON", "JSON_ENABLED"),
    )
    console_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("CONSOLE_ENABLED", "CONSOLE"),
    )
    request_body_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("REQUEST_BODY", "REQUEST_BODY_ENABLED"),
        description="是否在 request.log 记录 query/body（默认关，避免大 body 拖慢请求）。",
    )
    dir: str = Field(
        default="storage/logs",
        validation_alias=AliasChoices("DIR", "DIRECTORY"),
        description="日志根目录，其下按应用名分子目录。",
    )
    max_bytes: int = Field(default=10 * 1024 * 1024, description="rotating 单文件上限。")
    backup_count: int = Field(default=5, description="daily/rotating 保留份数。")

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
        if lowered not in {"single", "daily", "rotating"}:
            raise ValueError("LOG_DRIVER 必须为 single | daily | rotating")
        return lowered

    def resolved_level(self, *, app_debug: bool) -> str:
        if self.level is not None:
            return self.level
        return "DEBUG" if app_debug else "INFO"

    def app_log_dir(self, app_name: str) -> Path:
        """``storage/logs/{app-slug}/``，非扁平。"""
        base = Path(self.dir)
        if not base.is_absolute():
            base = BASE_DIR / base
        return base / _slugify_app_name(app_name)

    def channels(self, app_name: str, *, app_debug: bool) -> dict[str, LogChannel]:
        """声明通道 → 文件；``app.*`` 下 ``getLogger(__name__)`` 经 propagate 写入 ``app.log``。"""
        log_dir = self.app_log_dir(app_name)
        driver = self.driver
        level = self.resolved_level(app_debug=app_debug)

        def ch(logger: str, filename: str, *, ch_level: str | None = None) -> LogChannel:
            return LogChannel(
                logger=logger,
                filename=str(log_dir / filename),
                level=ch_level or level,
                driver=driver,
            )

        return {
            "app": ch("app", "app.log"),
            "request": ch("app.request", "request.log", ch_level="INFO"),
            "db": ch("sqlalchemy.engine", "db.log", ch_level="INFO"),
            "exception": ch("app.channel.exception", "exception.log", ch_level="WARNING"),
        }
