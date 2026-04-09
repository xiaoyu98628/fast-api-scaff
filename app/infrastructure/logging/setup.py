"""日志初始化实现：基础设施层负责日志通道组装与输出。"""

import logging
from logging import Formatter, Handler, Logger
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path

from app.infrastructure.logging.context import get_trace_id
from config.logging import LogChannel, LoggingSettings


class TraceIdFilter(logging.Filter):
    """保证所有日志记录都带 ``trace_id`` 字段。"""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "trace_id"):
            record.trace_id = get_trace_id()
        return True


def _build_file_handler(log_path: Path, channel: LogChannel, settings: LoggingSettings) -> Handler:
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
        # fallback: rotating 以保证未知 driver 不会导致日志中断
        handler = RotatingFileHandler(
            filename=log_path,
            maxBytes=settings.max_bytes,
            backupCount=settings.backup_count,
            encoding="utf-8",
            delay=True,
        )

    level_name = channel.level
    handler.setLevel(getattr(logging, level_name.upper(), logging.INFO))
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


def _resolve_default_handler_names(
    *,
    settings: LoggingSettings,
    channels: dict[str, LogChannel],
) -> list[str]:
    if settings.channel == "stack":
        base = [name for name in settings.stack_channels if name in channels]
        if not base:
            base = ["request", "error"]
    else:
        base = [settings.channel] if settings.channel in channels else []
    return base


def setup_logging(settings: LoggingSettings) -> None:
    """初始化多通道日志。"""
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(getattr(logging, settings.level.upper(), logging.INFO))

    channels = settings.channels
    channel_handlers = _build_channel_handlers(settings=settings, channels=channels)
    console_handler = _build_console_handler(settings) if settings.to_console else None
    default_handler_names = _resolve_default_handler_names(
        settings=settings,
        channels=channels,
    )
    default_handlers = [channel_handlers[name] for name in default_handler_names]
    if console_handler:
        default_handlers.append(console_handler)

    app_logger = logging.getLogger("app")
    _attach(app_logger, default_handlers, settings.level)

    request_channel: LogChannel = channels["request"]
    request_logger = logging.getLogger(request_channel.logger)
    _attach(
        request_logger,
        [channel_handlers["request"]] + ([console_handler] if console_handler else []),
        request_channel.level,
    )

    db_channel: LogChannel = channels["db"]
    db_logger = logging.getLogger(db_channel.logger)
    _attach(
        db_logger,
        [channel_handlers["db"]] + ([console_handler] if console_handler else []),
        db_channel.level,
    )

    db_pool_logger = logging.getLogger("sqlalchemy.pool")
    _attach(
        db_pool_logger,
        [channel_handlers["db"]] + ([console_handler] if console_handler else []),
        db_channel.level,
    )

    error_channel: LogChannel = channels["error"]
    error_logger = logging.getLogger(error_channel.logger)
    _attach(
        error_logger,
        [channel_handlers["error"]] + ([console_handler] if console_handler else []),
        error_channel.level,
    )

    debug_channel: LogChannel = channels["debug"]
    debug_logger = logging.getLogger(debug_channel.logger)
    _attach(
        debug_logger,
        [channel_handlers["debug"]] + ([console_handler] if console_handler else []),
        debug_channel.level,
    )

    # Laravel deprecations_channel 对齐：默认丢弃，按配置可接入已有通道
    py_warnings_logger = logging.getLogger("py.warnings")
    py_warnings_logger.handlers.clear()
    deprecations_name = settings.deprecations_channel
    if deprecations_name in channel_handlers:
        py_warnings_logger.addHandler(channel_handlers[deprecations_name])
    else:
        py_warnings_logger.addHandler(logging.NullHandler())
    py_warnings_logger.setLevel(logging.WARNING)
    py_warnings_logger.propagate = False
