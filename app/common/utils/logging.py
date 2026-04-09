"""日志初始化：按 default + stack + channels 组装。"""

import logging
from logging import Formatter, Handler, Logger
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config.logging import LogChannel, LoggingSettings


class TraceIdFilter(logging.Filter):
    """保证所有日志记录都带 ``trace_id`` 字段。"""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "trace_id"):
            record.trace_id = "-"
        return True


def _build_handler(log_path: Path, level_name: str, settings: LoggingSettings) -> Handler:
    handler = RotatingFileHandler(
        filename=log_path,
        maxBytes=settings.max_bytes,
        backupCount=settings.backup_count,
        encoding="utf-8",
    )
    handler.setLevel(getattr(logging, level_name.upper(), logging.INFO))
    handler.setFormatter(Formatter(settings.format, settings.date_format))
    handler.addFilter(TraceIdFilter())
    return handler


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


def _resolve_default_handlers(
    *,
    settings: LoggingSettings,
    channel_handlers: dict[str, Handler],
    console_handler: Handler | None,
) -> list[Handler]:
    if settings.channel == "stack":
        base = [channel_handlers[name] for name in settings.stack_channels if name in channel_handlers]
        if not base:
            base = [channel_handlers["request"], channel_handlers["error"]]
    else:
        base = [channel_handlers[settings.channel]] if settings.channel in channel_handlers else []
    if console_handler:
        base.append(console_handler)
    return base


def setup_logging(settings: LoggingSettings) -> None:
    """初始化多通道日志。"""
    log_dir = Path(settings.dir)
    if not log_dir.is_absolute():
        log_dir = Path.cwd() / log_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    # 先清空 root handlers，避免重复输出
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(getattr(logging, settings.level.upper(), logging.INFO))

    channels = settings.channels
    channel_handlers: dict[str, Handler] = {
        name: _build_handler(log_dir / channel.file, channel.level, settings)
        for name, channel in channels.items()
    }
    console_handler = _build_console_handler(settings) if settings.to_console else None
    default_handlers = _resolve_default_handlers(
        settings=settings,
        channel_handlers=channel_handlers,
        console_handler=console_handler,
    )

    # 业务默认 logger（给后续 service/agent/common 使用）
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
