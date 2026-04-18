"""日志注册：按通道挂载文件/控制台，统一接入请求日志与 SQLAlchemy 日志。"""

import logging
from logging import Formatter, Handler, Logger
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path

from app.infrastructure.logging.context import get_trace_id
from config.logging import LogChannel, LoggingSettings


class TraceIdFilter(logging.Filter):
    """为每条记录补上 ``trace_id``（供 format 使用）。"""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "trace_id"):
            record.trace_id = get_trace_id()
        return True


def _build_file_handler(log_path: Path, channel: LogChannel, settings: LoggingSettings) -> Handler:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    driver = channel.driver.lower()
    if driver == "single":
        handler = logging.FileHandler(filename=log_path, encoding="utf-8", delay=True)
    elif driver == "daily":
        handler = TimedRotatingFileHandler(
            filename=log_path,
            when="midnight",
            backupCount=settings.backup_count,
            encoding="utf-8",
            delay=True,
        )
    else:
        handler = RotatingFileHandler(
            filename=log_path,
            maxBytes=settings.max_bytes,
            backupCount=settings.backup_count,
            encoding="utf-8",
            delay=True,
        )

    handler.setLevel(getattr(logging, channel.level.upper(), logging.INFO))
    handler.setFormatter(Formatter(settings.format, settings.date_format))
    handler.addFilter(TraceIdFilter())
    return handler


def _resolve_channel_log_path(channel: LogChannel) -> Path:
    if not channel.path:
        raise ValueError(f"log channel `{channel.logger}` must define path")
    path = Path(channel.path)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def _build_console_handler(settings: LoggingSettings) -> Handler:
    handler = logging.StreamHandler()
    handler.setLevel(getattr(logging, settings.level.upper(), logging.INFO))
    handler.setFormatter(Formatter(settings.format, settings.date_format))
    handler.addFilter(TraceIdFilter())
    return handler


def _attach(logger: Logger, handlers: list[Handler], level_name: str) -> None:
    logger.handlers.clear()
    logger.setLevel(getattr(logging, level_name.upper(), logging.INFO))
    logger.propagate = False
    for h in handlers:
        logger.addHandler(h)


def _build_channel_handlers(
    *,
    settings: LoggingSettings,
    channels: dict[str, LogChannel],
) -> dict[str, Handler]:
    handlers: dict[str, Handler] = {}
    for name, channel in channels.items():
        if channel.driver.lower() == "null":
            handlers[name] = logging.NullHandler()
            continue
        log_path = _resolve_channel_log_path(channel)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers[name] = _build_file_handler(log_path, channel, settings)
    return handlers


def setup_logging(settings: LoggingSettings) -> None:
    """按配置注册各通道 logger；db 通道同时挂到 engine 与 pool。"""
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(getattr(logging, settings.level.upper(), logging.INFO))

    channels = settings.channels
    channel_handlers = _build_channel_handlers(settings=settings, channels=channels)
    console_handler = _build_console_handler(settings) if settings.to_console else None

    for name, ch in channels.items():
        lg = logging.getLogger(ch.logger)
        hlist: list[Handler] = [channel_handlers[name]]
        if console_handler:
            hlist.append(console_handler)
        _attach(lg, hlist, ch.level)

    if "db" in channels:
        db_ch = channels["db"]
        db_handlers: list[Handler] = [channel_handlers["db"]]
        if console_handler:
            db_handlers.append(console_handler)
        _attach(logging.getLogger("sqlalchemy.engine"), db_handlers, db_ch.level)
        _attach(logging.getLogger("sqlalchemy.pool"), db_handlers, db_ch.level)

    py_warnings_logger = logging.getLogger("py.warnings")
    py_warnings_logger.handlers.clear()
    py_warnings_logger.addHandler(logging.NullHandler())
    py_warnings_logger.setLevel(logging.WARNING)
    py_warnings_logger.propagate = False
