from app.config.settings import Settings
from app.infrastructure.logging.configure import configure_logging


def configure_worker_logging(settings: Settings) -> None:
    configure_logging(settings)
