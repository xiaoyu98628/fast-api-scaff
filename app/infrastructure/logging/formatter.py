"""把 LogRecord 格式化为具有稳定字段的 JSON 或文本日志。"""

import json
import logging
from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum


class _StructuredLogFormatter(logging.Formatter):
    """构建各输出格式共用的结构化日志字段。"""

    def __init__(self, *, service: str, environment: str, service_version: str) -> None:
        super().__init__()
        self._service = service
        self._environment = environment
        self._service_version = service_version

    def build_payload(self, record: logging.LogRecord) -> dict[str, object]:
        """提取通用字段及调用方提供的结构化扩展字段。"""

        payload: dict[str, object] = {
            "timestamp": _timestamp(record.created),
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
            # 复制映射，避免格式化阶段继续持有调用方的可变对象。
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
        """生成适合日志采集器逐行读取的紧凑 JSON。"""

        return _json_dumps(self.build_payload(record))


class TextLogFormatter(_StructuredLogFormatter):
    """将结构化日志字段转换成单行 key=value 文本。"""

    def format(self, record: logging.LogRecord) -> str:
        """生成人工阅读友好的单行键值文本。"""

        payload = self.build_payload(record)
        return " ".join(f"{key}={_json_dumps(value)}" for key, value in payload.items())


def _json_dumps(value: object) -> str:
    """稳定序列化日志值，并兼容调用方传入的非 JSON 对象。"""

    # 日志格式化失败不应遮蔽原始业务错误，因此未知对象降级为字符串。
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _timestamp(created: float) -> str:
    """把 LogRecord 时间转换成本机时区的毫秒级 ISO 8601 文本。"""

    return datetime.fromtimestamp(created).astimezone().isoformat(timespec="milliseconds")
