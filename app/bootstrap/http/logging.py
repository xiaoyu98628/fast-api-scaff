from enum import StrEnum

from app.config.settings import Settings
from app.infrastructure.logging.configure import configure_logging


class ApplicationLogEvent(StrEnum):
    STARTING = "application.starting"
    STARTED = "application.started"
    START_FAILED = "application.start_failed"
    STOPPING = "application.stopping"
    STOPPED = "application.stopped"
    STOP_FAILED = "application.stop_failed"


def configure_http_logging(settings: Settings) -> None:
    configure_logging(settings)
