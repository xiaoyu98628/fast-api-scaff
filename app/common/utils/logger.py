"""业务日志入口：``Log.info("...")``，通道与 ``config.logging.LoggingSettings.channels`` 的 key 对齐。"""

import logging
from typing import Any, ClassVar

__all__ = ["Log"]


class Log:
    """类方法写日志；默认通道 ``request``。"""

    # 与 LoggingSettings.channels 的 key 一致；新增通道时在此补充
    CHANNEL_LOGGER_MAP: ClassVar[dict[str, str]] = {
        "request": "app.request",
        "db": "sqlalchemy.engine",
    }

    @classmethod
    def get_logger(cls, channel: str = "request") -> logging.Logger:
        name = cls.CHANNEL_LOGGER_MAP.get(channel, f"app.{channel}")
        return logging.getLogger(name)

    @classmethod
    def _emit(
        cls,
        level: int,
        message: str,
        *args: Any,
        channel: str = "request",
        trace_id: str | None = None,
        extra: dict[str, Any] | None = None,
        exc_info: bool = False,
    ) -> None:
        payload = dict(extra or {})
        if trace_id is not None:
            payload["trace_id"] = trace_id
        logger = cls.get_logger(channel)
        logger.log(level, message, *args, extra=payload or None, exc_info=exc_info)

    @classmethod
    def debug(
        cls,
        message: str,
        *args: Any,
        channel: str = "request",
        trace_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        cls._emit(logging.DEBUG, message, *args, channel=channel, trace_id=trace_id, extra=extra)

    @classmethod
    def info(
        cls,
        message: str,
        *args: Any,
        channel: str = "request",
        trace_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        cls._emit(logging.INFO, message, *args, channel=channel, trace_id=trace_id, extra=extra)

    @classmethod
    def warning(
        cls,
        message: str,
        *args: Any,
        channel: str = "request",
        trace_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        cls._emit(logging.WARNING, message, *args, channel=channel, trace_id=trace_id, extra=extra)

    @classmethod
    def error(
        cls,
        message: str,
        *args: Any,
        channel: str = "request",
        trace_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        cls._emit(logging.ERROR, message, *args, channel=channel, trace_id=trace_id, extra=extra)

    @classmethod
    def exception(
        cls,
        message: str,
        *args: Any,
        channel: str = "request",
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
