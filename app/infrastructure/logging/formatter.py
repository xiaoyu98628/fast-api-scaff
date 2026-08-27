import json
import logging
from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from zoneinfo import ZoneInfo


class _StructuredLogFormatter(logging.Formatter):
    """构建各输出格式共用的结构化日志字段。"""

    def __init__(self, *, service: str, environment: str, service_version: str, timezone: str) -> None:
        super().__init__()
        self._service = service
        self._environment = environment
        self._service_version = service_version
        self._timezone = timezone

    def build_payload(self, record: logging.LogRecord) -> dict[str, object]:
        payload: dict[str, object] = {
            "timestamp": _timestamp(record.created, self._timezone),
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

        return payload


class JsonLogFormatter(_StructuredLogFormatter):
    """将日志记录转换成单行 JSON。"""

    def format(self, record: logging.LogRecord) -> str:
        return _json_dumps(self.build_payload(record))


class TextLogFormatter(_StructuredLogFormatter):
    """将结构化日志字段转换成单行 key=value 文本。"""

    def format(self, record: logging.LogRecord) -> str:
        payload = self.build_payload(record)
        return " ".join(f"{key}={_json_dumps(value)}" for key, value in payload.items())


def _json_dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _timestamp(created: float, timezone: str) -> str:
    timestamp = datetime.fromtimestamp(created, tz=ZoneInfo(timezone))
    rendered = timestamp.isoformat(timespec="milliseconds")
    return f"{rendered.removesuffix('+00:00')}Z" if rendered.endswith("+00:00") else rendered
