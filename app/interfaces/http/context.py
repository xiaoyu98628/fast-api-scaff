"""提供 HTTP 入站适配器读取当前请求上下文的稳定入口。"""

from starlette_context import context
from starlette_context.header_keys import HeaderKeys


def require_request_id() -> str:
    """返回中间件已经校验的请求标识；上下文契约失效时抛出 RuntimeError。"""

    if not context.exists():
        raise RuntimeError("当前 HTTP 请求上下文不存在")

    try:
        return str(context[HeaderKeys.request_id])
    except KeyError, RuntimeError:
        raise RuntimeError("当前 HTTP 请求缺少 request ID") from None
