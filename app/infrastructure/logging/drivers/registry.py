from app.infrastructure.logging.contracts.driver import LoggingDriverBuilder
from app.infrastructure.logging.drivers.stream import build_stream_handler

DEFAULT_LOGGING_DRIVERS: dict[str, LoggingDriverBuilder] = {
    "stream": build_stream_handler,
}
