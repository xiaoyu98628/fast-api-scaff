"""日志配置：统一定义基础通道（app/request/db/error），便于按场景拆分日志文件。"""

from typing import Dict

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

from config import BASE_DIR, LOG_DIR


class LogChannel(BaseModel):
    """单个日志通道：logger 名称 + 写入策略 + 级别 + 路径。"""

    logger: str
    driver: str = "single"
    level: str
    path: str | None = None


class LoggingSettings(BaseSettings):
    """日志相关环境变量（前缀 ``LOG_``）。"""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR.joinpath(".env"),
        env_file_encoding="utf-8",
        env_prefix="LOG_",
        extra="ignore",
    )

    level: str = "INFO"
    driver: str = "single"
    to_console: bool = True
    format: str = "[%(asctime)s] | %(levelname)s | %(name)s | trace_id=%(trace_id)s | %(message)s"
    date_format: str = "%Y-%m-%d %H:%M:%S"
    max_bytes: int = 10 * 1024 * 1024
    backup_count: int = 5

    @property
    def channels(self) -> Dict[str, LogChannel]:
        return {
            "app": LogChannel(
                logger="app",
                driver=self.driver,
                level=self.level,
                path=str(LOG_DIR / "log" / "app.log"),
            ),
            "request": LogChannel(
                logger="app.request",
                driver=self.driver,
                level=self.level,
                path=str(LOG_DIR / "log" / "request.log"),
            ),
            "db": LogChannel(
                logger="sqlalchemy.engine",
                driver=self.driver,
                level=self.level,
                path=str(LOG_DIR / "log" / "db.log"),
            ),
            "exception": LogChannel(
                logger="exception",
                driver=self.driver,
                level=self.level,
                path=str(LOG_DIR / "log" / "exception.log"),
            ),
            "error": LogChannel(
                logger="error",
                driver=self.driver,
                level=self.level,
                path=str(LOG_DIR / "log" / "error.log"),
            ),
            "debug": LogChannel(
                logger="debug",
                driver=self.driver,
                level=self.level,
                path=str(LOG_DIR / "log" / "debug.log"),
            ),
        }
