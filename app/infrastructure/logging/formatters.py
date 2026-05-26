import json
import logging
from datetime import UTC, datetime
from typing import Any

DEFAULT_LOG_FORMAT = "[%(asctime)s] | %(levelname)s | %(name)s | trace_id=%(trace_id)s | %(message)s"
DEFAULT_LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class JsonFormatter(logging.Formatter):
    """将 LogRecord 格式化为单行 JSON。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "trace_id": getattr(record, "trace_id", "-"),
            "message": record.getMessage(),
        }

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        for key, value in record.__dict__.items():
            if key.startswith("_") or key in {
                "name",
                "msg",
                "args",
                "created",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "message",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "exc_info",
                "exc_text",
                "thread",
                "threadName",
                "taskName",
            }:
                continue
            payload[key] = value

        return json.dumps(payload, ensure_ascii=False, default=str)


def build_text_formatter() -> logging.Formatter:
    return logging.Formatter(DEFAULT_LOG_FORMAT, DEFAULT_LOG_DATE_FORMAT)


def build_formatter(*, json_enabled: bool) -> logging.Formatter:
    if json_enabled:
        return JsonFormatter()
    return build_text_formatter()
