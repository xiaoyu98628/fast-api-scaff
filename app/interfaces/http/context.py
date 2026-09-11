"""提供 HTTP 入站适配器读取当前请求上下文的稳定入口。"""

from starlette_context import context
from starlette_context.header_keys import HeaderKeys


def current_request_id() -> str | None:
    """返回中间件已经校验的请求标识；无请求上下文时返回 None。"""

    if not context.exists():
        return None

    try:
        return str(context[HeaderKeys.request_id])
    except KeyError, RuntimeError:
        return None
