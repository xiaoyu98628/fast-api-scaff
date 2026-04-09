"""统一日志封装：业务代码直接调用，避免散落 getLogger。"""

import logging
from typing import Any

CHANNEL_LOGGER_MAP = {
    "request": "app.request",
    "db": "sqlalchemy.engine",
    "error": "app.error",
    "debug": "app.debug",
}


def get_channel_logger(channel: str = "debug") -> logging.Logger:
    logger_name = CHANNEL_LOGGER_MAP.get(channel, f"app.{channel}")
    return logging.getLogger(logger_name)


def app_log(
    level: int,
    message: str,
    *args: Any,
    channel: str = "debug",
    trace_id: str | None = None,
    extra: dict[str, Any] | None = None,
    exc_info: bool = False,
) -> None:
    payload = dict(extra or {})
    if trace_id is not None:
        payload["trace_id"] = trace_id

    logger = get_channel_logger(channel)
    logger.log(level, message, *args, extra=payload or None, exc_info=exc_info)


def log_debug(message: str, *args: Any, channel: str = "debug", **kwargs: Any) -> None:
    app_log(logging.DEBUG, message, *args, channel=channel, **kwargs)


def log_info(message: str, *args: Any, channel: str = "debug", **kwargs: Any) -> None:
    app_log(logging.INFO, message, *args, channel=channel, **kwargs)


def log_warning(message: str, *args: Any, channel: str = "debug", **kwargs: Any) -> None:
    app_log(logging.WARNING, message, *args, channel=channel, **kwargs)


def log_error(message: str, *args: Any, channel: str = "error", **kwargs: Any) -> None:
    app_log(logging.ERROR, message, *args, channel=channel, **kwargs)


def log_exception(message: str, *args: Any, channel: str = "error", **kwargs: Any) -> None:
    app_log(logging.ERROR, message, *args, channel=channel, exc_info=True, **kwargs)

