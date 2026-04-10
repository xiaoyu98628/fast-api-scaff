"""日志配置：通道定义在此，新增通道时往 ``channels`` 里加一项即可。"""

from datetime import datetime

from pydantic import BaseModel, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from config import BASE_DIR, LOG_DIR


class LogChannel(BaseModel):
    """单个日志通道：底层 logger 名 + 落盘文件名 + 级别。"""

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
    """日志相关环境变量（前缀 ``LOG_``）。"""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR.joinpath(".env"),
        env_file_encoding="utf-8",
        env_prefix="LOG_",
        extra="ignore",
    )

    level: str = "INFO"
    to_console: bool = True
    format: str = "%(asctime)s | %(levelname)s | %(name)s | trace_id=%(trace_id)s | %(message)s"
    date_format: str = "%Y-%m-%d %H:%M:%S"
    max_bytes: int = 10 * 1024 * 1024
    backup_count: int = 5

    @property
    def channels(self) -> dict[str, LogChannel]:
        """具名通道：key 用于注册与 util 中的 channel 名。扩展时在此追加条目。"""
        lv = self.level
        return {
            "request": build_channel("app.request", level=lv, filename="request.log"),
            "db": build_channel("sqlalchemy.engine", level=lv, filename="db.log"),
        }

    @field_validator("level", mode="before")
    @classmethod
    def normalize_level_value(cls, value: str) -> str:
        return str(value).upper()
