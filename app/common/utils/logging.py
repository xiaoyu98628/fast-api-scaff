"""日志初始化：按 default + stack + channels 组装。"""

import logging
from logging import Formatter, Handler, Logger
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config.logging import LoggingSettings


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
    request_handler: Handler,
    db_handler: Handler,
    error_handler: Handler,
    console_handler: Handler | None,
) -> list[Handler]:
    if settings.channel == "request":
        base = [request_handler]
    elif settings.channel == "db":
        base = [db_handler]
    elif settings.channel == "error":
        base = [error_handler]
    else:
        # stack
        mapping = {
            "request": request_handler,
            "db": db_handler,
            "error": error_handler,
        }
        base = [mapping[name] for name in settings.stack_channels if name in mapping]
        if not base:
            base = [request_handler, error_handler]
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

    request_handler = _build_handler(log_dir / settings.request_file, settings.request_level, settings)
    db_handler = _build_handler(log_dir / settings.db_file, settings.db_level, settings)
    error_handler = _build_handler(log_dir / settings.error_file, settings.error_level, settings)
    console_handler = _build_console_handler(settings) if settings.to_console else None
    default_handlers = _resolve_default_handlers(
        settings=settings,
        request_handler=request_handler,
        db_handler=db_handler,
        error_handler=error_handler,
        console_handler=console_handler,
    )

    # 业务默认 logger（给后续 service/agent/common 使用）
    app_logger = logging.getLogger("app")
    _attach(app_logger, default_handlers, settings.level)

    request_logger = logging.getLogger("app.request")
    _attach(
        request_logger,
        [request_handler] + ([console_handler] if console_handler else []),
        settings.request_level,
    )

    db_logger = logging.getLogger("sqlalchemy.engine")
    _attach(
        db_logger,
        [db_handler] + ([console_handler] if console_handler else []),
        settings.db_level,
    )

    db_pool_logger = logging.getLogger("sqlalchemy.pool")
    _attach(
        db_pool_logger,
        [db_handler] + ([console_handler] if console_handler else []),
        settings.db_level,
    )

    error_logger = logging.getLogger("app.error")
    _attach(
        error_logger,
        [error_handler] + ([console_handler] if console_handler else []),
        settings.error_level,
    )
