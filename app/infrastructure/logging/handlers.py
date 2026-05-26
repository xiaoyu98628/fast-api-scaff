import logging
from logging import Formatter, Handler
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path

from app.infrastructure.logging.filters import TraceIdFilter
from config.logging import LogChannel, LoggingConfig

DEFAULT_LOG_FORMAT = "[%(asctime)s] | %(levelname)s | %(name)s | trace_id=%(trace_id)s | %(message)s"
DEFAULT_LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class _EnsureLogDirMixin:
    """配合 ``delay=True``：首次 ``emit`` 时再创建目录与日志文件。"""

    def _open(self):
        Path(self.baseFilename).parent.mkdir(parents=True, exist_ok=True)
        return super()._open()


class LazyFileHandler(_EnsureLogDirMixin, logging.FileHandler):
    pass


class LazyRotatingFileHandler(_EnsureLogDirMixin, RotatingFileHandler):
    pass


class LazyTimedRotatingFileHandler(_EnsureLogDirMixin, TimedRotatingFileHandler):
    pass


def _configure_handler(handler: Handler, *, level_name: str, json_enabled: bool) -> Handler:
    handler.setLevel(getattr(logging, level_name.upper(), logging.DEBUG))
    if json_enabled:
        from app.infrastructure.logging.formatters import JsonFormatter

        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(Formatter(DEFAULT_LOG_FORMAT, DEFAULT_LOG_DATE_FORMAT))
    handler.addFilter(TraceIdFilter())
    return handler


def build_file_handler(log_path: str | Path, channel: LogChannel, settings: LoggingConfig) -> Handler:
    log_path = Path(log_path)
    driver = channel.driver.lower()

    if driver == "daily":
        handler: Handler = LazyTimedRotatingFileHandler(
            filename=log_path,
            when="midnight",
            backupCount=settings.backup_count,
            encoding="utf-8",
            delay=True,
        )
    elif driver == "rotating":
        handler = LazyRotatingFileHandler(
            filename=log_path,
            maxBytes=settings.max_bytes,
            backupCount=settings.backup_count,
            encoding="utf-8",
            delay=True,
        )
    else:
        handler = LazyFileHandler(filename=log_path, encoding="utf-8", delay=True)

    return _configure_handler(handler, level_name=channel.level, json_enabled=settings.json_enabled)


def build_console_handler(settings: LoggingConfig, *, level_name: str) -> Handler:
    handler = logging.StreamHandler()
    return _configure_handler(handler, level_name=level_name, json_enabled=settings.json_enabled)
