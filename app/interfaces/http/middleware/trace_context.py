"""把已校验的 HTTP Request ID 绑定为宿主无关的追踪上下文。"""

from starlette.types import ASGIApp, Receive, Scope, Send
from starlette_context import context
from starlette_context.header_keys import HeaderKeys

from app.runtime.trace import TraceContext, bind_trace_context


class TraceContextMiddleware:
    """在完整 HTTP 请求及其后台任务期间绑定追踪上下文。"""

    def __init__(self, app: ASGIApp) -> None:
        """保存下一层 ASGI 应用。"""

        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """让当前 Request ID 自动成为下游队列消息的关联 ID。"""

        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _read_request_id()
        trace_context = TraceContext(
            correlation_id=request_id,
            request_id=request_id,
        )
        # Starlette 在响应调用返回前执行 BackgroundTask，因此该作用域覆盖后台发布。
        with bind_trace_context(trace_context):
            await self.app(scope, receive, send)


def _read_request_id() -> str:
    """读取外层中间件已经校验的 Request ID。"""

    if not context.exists():
        raise RuntimeError("当前 HTTP 请求上下文不存在")

    try:
        return str(context[HeaderKeys.request_id])
    except KeyError, RuntimeError:
        raise RuntimeError("当前 HTTP 请求缺少 request ID") from None
