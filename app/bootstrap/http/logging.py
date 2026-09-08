"""定义 HTTP 宿主生命周期事件并配置其日志。"""

from enum import StrEnum

from app.config.settings import Settings
from app.infrastructure.logging.configure import configure_logging


class ApplicationLogEvent(StrEnum):
    """应用启动与关闭阶段使用的稳定结构化事件名。"""

    STARTING = "application.starting"
    STARTED = "application.started"
    START_FAILED = "application.start_failed"
    STOPPING = "application.stopping"
    STOPPED = "application.stopped"
    STOP_FAILED = "application.stop_failed"


def configure_http_logging(settings: Settings) -> None:
    """使用应用统一约定配置 HTTP 进程日志。"""

    configure_logging(settings)
