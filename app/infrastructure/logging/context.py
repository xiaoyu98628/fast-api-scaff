import logging

from starlette_context import context
from starlette_context.header_keys import HeaderKeys


class RequestContextFilter(logging.Filter):
    """在日志进入 Handler 时固化当前请求上下文。"""

    def filter(self, record: logging.LogRecord) -> bool:
        if getattr(record, "request_id", None) is None:
            setattr(record, "request_id", _get_request_id())

        return True


def _get_request_id() -> str | None:
    if not context.exists():
        return None

    try:
        return str(context[HeaderKeys.request_id])
    except KeyError, RuntimeError:
        return None
