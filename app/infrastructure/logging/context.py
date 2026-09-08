"""把当前 HTTP 请求标识补充到 LogRecord。"""

import logging

from starlette_context import context
from starlette_context.header_keys import HeaderKeys


class RequestContextFilter(logging.Filter):
    """在日志进入 Handler 时固化当前请求上下文。"""

    def filter(self, record: logging.LogRecord) -> bool:
        """补充缺失的 request_id，并允许日志继续输出。"""

        # 显式传入的 request_id 优先，避免覆盖后台任务等调用方提供的上下文。
        if getattr(record, "request_id", None) is None:
            setattr(record, "request_id", _get_request_id())

        return True


def _get_request_id() -> str | None:
    """安全读取当前 Starlette 上下文中的请求标识。"""

    # 启动期、后台任务和 Console 都可能在 HTTP 请求之外记录日志。
    if not context.exists():
        return None

    try:
        return str(context[HeaderKeys.request_id])
    except KeyError, RuntimeError:
        return None
