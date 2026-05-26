"""请求作用域中间件：trace id + ContextVar（Request / 头 / extra）。"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.infrastructure.context.request_scope import TRACE_ID_HEADER_DEFAULT, bind_request_scope


class RequestScopeMiddleware(BaseHTTPMiddleware):
    """为每个请求注入 trace id，并绑定请求级 ContextVar。"""

    trace_id_header = TRACE_ID_HEADER_DEFAULT

    async def dispatch(self, request: Request, call_next):
        tokens = bind_request_scope(request, trace_id_header=self.trace_id_header)
        try:
            response = await call_next(request)
            response.headers[self.trace_id_header] = getattr(request.state, "trace_id", "")
            return response
        finally:
            tokens.reset_all()
