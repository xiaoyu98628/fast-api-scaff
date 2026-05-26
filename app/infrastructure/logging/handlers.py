import logging
from logging import Handler
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path

from app.infrastructure.logging.channel import ChannelDefinition
from app.infrastructure.logging.filters import TraceIdFilter
from app.infrastructure.logging.formatters import build_formatter
from config.logging import LoggingConfig


def _ensure_log_file(base_filename: str) -> None:
    """``delay=True`` 下首次 ``_open`` 调用：仅当目标文件不存在时创建目录。"""
    log_path = Path(base_filename)
    if log_path.exists():
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)


class _LazyOpenMixin:
    def _open(self):
        _ensure_log_file(self.baseFilename)
        return super()._open()


class LazyFileHandler(_LazyOpenMixin, logging.FileHandler):
    pass


class LazyRotatingFileHandler(_LazyOpenMixin, RotatingFileHandler):
    pass


class LazyTimedRotatingFileHandler(_LazyOpenMixin, TimedRotatingFileHandler):
    pass


def _configure_handler(handler: Handler, *, level_name: str, json_enabled: bool) -> Handler:
    handler.setLevel(getattr(logging, level_name.upper(), logging.DEBUG))
    handler.setFormatter(build_formatter(json_enabled=json_enabled))
    handler.addFilter(TraceIdFilter())
    return handler


def build_file_handler(log_path: str | Path, channel: ChannelDefinition, settings: LoggingConfig) -> Handler:
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
