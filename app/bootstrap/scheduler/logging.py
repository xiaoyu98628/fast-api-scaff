"""定义 Scheduler 宿主生命周期事件并配置日志。"""

from enum import StrEnum

from app.config.settings import Settings
from app.infrastructure.logging.configure import configure_logging


class SchedulerLogEvent(StrEnum):
    """Scheduler 启动与关闭阶段使用的稳定结构化事件名。"""

    STARTING = "scheduler.starting"
    SCHEDULES_DISCOVERED = "scheduler.schedules_discovered"
    STARTED = "scheduler.started"
    START_FAILED = "scheduler.start_failed"
    STOPPING = "scheduler.stopping"
    STOPPED = "scheduler.stopped"
    STOP_FAILED = "scheduler.stop_failed"


def configure_scheduler_logging(settings: Settings) -> None:
    """使用与其他宿主一致的结构化日志配置。"""

    configure_logging(settings)
