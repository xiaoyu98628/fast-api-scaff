"""日志配置（Laravel 风格简化版）：default + stack + channels。"""

from pydantic import field_validator
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

from config import BASE_DIR


class LogChannel(BaseModel):
    """单个日志通道配置。"""

    logger: str
    level: str
    file: str


class LoggingSettings(BaseSettings):
    """日志配置（前缀 ``LOG_``）。"""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR.joinpath(".env"),
        env_file_encoding="utf-8",
        env_prefix="LOG_",
        extra="ignore",
    )

    # default/stack 风格
    channel: str = "stack"
    stack: str = "request,error"

    # 全局通用配置
    dir: str = "logs"
    level: str = "INFO"
    to_console: bool = True
    format: str = "%(asctime)s | %(levelname)s | %(name)s | trace_id=%(trace_id)s | %(message)s"
    date_format: str = "%Y-%m-%d %H:%M:%S"
    max_bytes: int = 10 * 1024 * 1024
    backup_count: int = 5

    # 通道配置（字典化）
    request_level: str = "INFO"
    request_file: str = "request.log"

    db_level: str = "INFO"
    db_file: str = "db.log"

    error_level: str = "ERROR"
    error_file: str = "error.log"

    debug_level: str = "DEBUG"
    debug_file: str = "debug.log"

    @property
    def stack_channels(self) -> list[str]:
        return [x.strip() for x in self.stack.split(",") if x.strip()]

    @property
    def channels(self) -> dict[str, LogChannel]:
        return {
            "request": LogChannel(logger="app.request", level=self.request_level, file=self.request_file),
            "db": LogChannel(logger="sqlalchemy.engine", level=self.db_level, file=self.db_file),
            "error": LogChannel(logger="app.error", level=self.error_level, file=self.error_file),
            "debug": LogChannel(logger="app.debug", level=self.debug_level, file=self.debug_file),
        }

    @field_validator(
        "level",
        "request_level",
        "db_level",
        "error_level",
        "debug_level",
        mode="before",
    )
    @classmethod
    def normalize_level_value(cls, value: str) -> str:
        return str(value).upper()
