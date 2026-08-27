import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum


class JsonLogFormatter(logging.Formatter):
    """将日志记录转换成单行 JSON。"""

    def __init__(self, *, service: str, environment: str, service_version: str) -> None:
        super().__init__()
        self._service = service
        self._environment = environment
        self._service_version = service_version

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": _utc_timestamp(record.created),
            "level": record.levelname,
            "logger": record.name,
            "service": self._service,
            "environment": self._environment,
            "service_version": self._service_version,
            "message": record.getMessage(),
        }

        request_id = getattr(record, "request_id", None)
        if request_id is not None:
            payload["request_id"] = str(request_id)

        event = getattr(record, "event", None)
        if isinstance(event, StrEnum):
            payload["event"] = event.value
        elif isinstance(event, str):
            payload["event"] = event

        details = getattr(record, "details", None)
        if isinstance(details, Mapping):
            payload["details"] = dict(details)

        if record.exc_info and record.exc_info[0] is not None:
            exception_type, exception, _traceback = record.exc_info
            payload["exception"] = {
                "type": exception_type.__name__,
                "message": str(exception) if exception is not None else None,
                "stacktrace": self.formatException(record.exc_info),
            }

        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)


def _utc_timestamp(created: float) -> str:
    timestamp = datetime.fromtimestamp(created, tz=UTC)
    return timestamp.isoformat(timespec="milliseconds").replace("+00:00", "Z")
