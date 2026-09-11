"""配置独立 Worker 进程使用的应用日志。"""

from enum import StrEnum

from app.config.settings import Settings
from app.infrastructure.logging.configure import configure_logging


class WorkerLogEvent(StrEnum):
    """Worker 启动与关闭阶段使用的稳定结构化事件名。"""

    STARTING = "worker.starting"
    STARTED = "worker.started"
    START_FAILED = "worker.start_failed"
    STOPPING = "worker.stopping"
    STOPPED = "worker.stopped"
    STOP_FAILED = "worker.stop_failed"


def configure_worker_logging(settings: Settings) -> None:
    """使用与其他宿主一致的结构化日志配置。"""

    configure_logging(settings)
