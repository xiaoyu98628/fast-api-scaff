"""日志配置（Laravel 风格）：default + stack + channels + driver。"""

from datetime import datetime

from pydantic import field_validator
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

from config import BASE_DIR, LOG_DIR


class LogChannel(BaseModel):
    """单个日志通道配置。"""

    logger: str
    driver: str = "single"
    level: str
    file: str
    path: str | None = None
    replace_placeholders: bool = True


def build_daily_log_path(filename: str) -> str:
    daily_dir = LOG_DIR / datetime.now().strftime("%Y-%m-%d")
    return str(daily_dir / filename)


def build_channel(logger: str, *, level: str, filename: str) -> LogChannel:
    return LogChannel(
        logger=logger,
        level=level,
        file=filename,
        path=build_daily_log_path(filename),
    )


class LoggingSettings(BaseSettings):
    """日志配置（前缀 ``LOG_``）。"""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR.joinpath(".env"),
        env_file_encoding="utf-8",
        env_prefix="LOG_",
        extra="ignore",
    )

    # Laravel 风格：default + deprecations + channels
    channel: str = "stack"
    stack: str = "request,error"
    deprecations_channel: str = "null"

    # 全局通用配置
    # level：控制台、根 logger、app 汇总，以及 request / db / debug 三个文件通道的级别（一处调节）
    level: str = "INFO"
    to_console: bool = True
    format: str = "%(asctime)s | %(levelname)s | %(name)s | trace_id=%(trace_id)s | %(message)s"
    date_format: str = "%Y-%m-%d %H:%M:%S"
    max_bytes: int = 10 * 1024 * 1024
    backup_count: int = 5  # daily 场景下等同 days

    # error 通道单独级别（error.log 通常保持 ERROR，与访问/SQL 粒度解耦）
    error_level: str = "ERROR"
    error_file: str = "error.log"
    debug_file: str = "debug.log"

    @property
    def stack_channels(self) -> list[str]:
        return [x.strip() for x in self.stack.split(",") if x.strip()]

    @property
    def channels(self) -> dict[str, LogChannel]:
        lv = self.level
        return {
            "request": build_channel("app.request", level=lv, filename="request.log"),
            "db": build_channel("sqlalchemy.engine", level=lv, filename="db.log"),
            "error": build_channel("app.error", level=self.error_level, filename=self.error_file),
            "debug": build_channel("app.debug", level=lv, filename=self.debug_file),
        }

    @field_validator(
        "level",
        "error_level",
        mode="before",
    )
    @classmethod
    def normalize_level_value(cls, value: str) -> str:
        return str(value).upper()

    @field_validator("channel", "deprecations_channel", mode="before")
    @classmethod
    def normalize_channel_name(cls, value: str) -> str:
        return str(value).strip().lower()
