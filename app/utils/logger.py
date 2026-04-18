"""业务日志入口。"""

import logging
from typing import Any, ClassVar


class Log:
    """类方法写日志；默认通道 ``app``。"""

    CHANNEL_LOGGER_MAP: ClassVar[dict[str, str]] = {
        "app": "app",
        "request": "app.request",
        "db": "sqlalchemy.engine",
        "error": "error",
        "exception": "exception",
        "debug": "debug",
    }

    @classmethod
    def get_logger(cls, channel: str = "app") -> logging.Logger:
        name = cls.CHANNEL_LOGGER_MAP.get(channel, f"app.{channel}")
        return logging.getLogger(name)

    @classmethod
    def _emit(
        cls,
        level: int,
        message: str,
        *args: Any,
        channel: str = "app",
        trace_id: str | None = None,
        extra: dict[str, Any] | None = None,
        exc_info: bool = False,
    ) -> None:
        payload = dict(extra or {})
        if trace_id is not None:
            payload["trace_id"] = trace_id
        logger = cls.get_logger(channel)
        try:
            logger.log(level, message, *args, extra=payload or None, exc_info=exc_info)
        except Exception:
            logging.getLogger().exception("log emit failed: channel=%s message=%s", channel, message)

    @classmethod
    def debug(
        cls,
        message: str,
        *args: Any,
        channel: str = "debug",
        trace_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        cls._emit(
            logging.DEBUG,
            message,
            *args,
            channel=channel,
            trace_id=trace_id,
            extra=extra,
            exc_info=True,
        )

    @classmethod
    def info(
        cls,
        message: str,
        *args: Any,
        channel: str = "app",
        trace_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        cls._emit(logging.INFO, message, *args, channel=channel, trace_id=trace_id, extra=extra)

    @classmethod
    def warning(
        cls,
        message: str,
        *args: Any,
        channel: str = "app",
        trace_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        cls._emit(logging.WARNING, message, *args, channel=channel, trace_id=trace_id, extra=extra)

    @classmethod
    def error(
        cls,
        message: str,
        *args: Any,
        channel: str = "error",
        trace_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        cls._emit(
            logging.ERROR,
            message,
            *args,
            channel=channel,
            trace_id=trace_id,
            extra=extra,
            exc_info=True,
        )

    @classmethod
    def exception(
        cls,
        message: str,
        *args: Any,
        channel: str = "error",
        trace_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        cls._emit(
            logging.INFO,
            message,
            *args,
            channel=channel,
            trace_id=trace_id,
            extra=extra,
            exc_info=True,
        )
