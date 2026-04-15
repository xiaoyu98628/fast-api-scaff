"""日志配置：通道定义在此，新增通道时往 ``channels`` 里加一项即可。"""

from typing import Dict
from datetime import datetime

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

from config import BASE_DIR, LOG_DIR


class LogChannel(BaseModel):
    """单个日志通道：底层 logger 名 + 落盘文件名 + 级别。"""

    driver: str = "single" # single：写入单个固定文件，daily：按天写入不同文件
    level: str
    path: str | None = None


def build_daily_log_path(filename: str) -> str:
    daily_dir = LOG_DIR / datetime.now().strftime("%Y-%m-%d")
    return str(daily_dir / filename)

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
    format: str = "%(asctime)s | %(levelname)s | %(name)s | trace_id=%(trace_id)s | %(message)s"
    date_format: str = "%Y-%m-%d %H:%M:%S"
    max_bytes: int = 10 * 1024 * 1024
    backup_count: int = 5

    @property
    def channels(self) -> Dict[str, LogChannel]:
        """具名通道：key 用于注册与 util 中的 channel 名。扩展时在此追加条目。"""
        return {
            "single": LogChannel(driver=self.driver, level=self.level, path=""),
            "request": LogChannel(driver="single", level=self.level, path=""),
            "db": LogChannel(driver="single", level=self.level, path=""),
        }
