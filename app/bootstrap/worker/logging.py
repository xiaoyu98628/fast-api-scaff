"""配置独立 Worker 进程使用的应用日志。"""

from app.config.settings import Settings
from app.infrastructure.logging.configure import configure_logging


def configure_worker_logging(settings: Settings) -> None:
    """使用与其他宿主一致的结构化日志配置。"""

    configure_logging(settings)
