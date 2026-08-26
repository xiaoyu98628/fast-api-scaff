import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum

from starlette_context import context
from starlette_context.header_keys import HeaderKeys


class JsonLogFormatter(logging.Formatter):
    """将日志记录转换成单行 JSON。"""

    def __init__(self, *, service: str, environment: str) -> None:
        super().__init__()
        self._service = service
        self._environment = environment

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": _utc_timestamp(),
            "level": record.levelname,
            "logger": record.name,
            "service": self._service,
            "environment": self._environment,
            "message": record.getMessage(),
        }

        request_id = _get_request_id()
        if request_id is not None:
            payload["request_id"] = request_id

        event = getattr(record, "event", None)
        if isinstance(event, StrEnum):
            payload["event"] = event.value
        elif isinstance(event, str):
            payload["event"] = event

        details = getattr(record, "details", None)
        if isinstance(details, Mapping):
            payload["details"] = dict(details)

        if record.exc_info is not None:
            exception_type, exception, _traceback = record.exc_info
            payload["exception"] = {
                "type": exception_type.__name__ if exception_type is not None else None,
                "message": str(exception) if exception is not None else None,
                "stacktrace": self.formatException(record.exc_info),
            }

        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _get_request_id() -> str | None:
    if not context.exists():
        return None

    try:
        return str(context[HeaderKeys.request_id])
    except (KeyError, RuntimeError):
        return None
