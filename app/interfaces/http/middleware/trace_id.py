
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class TraceIdMiddleware(BaseHTTPMiddleware):
    """将 trace_id 添加到每个请求的响应头。"""

    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get("X-Trace-Id")

        if not trace_id:
            trace_id = str(uuid.uuid4())
        request.state.trace_id = trace_id

        response = await call_next(request)
        response.headers["X-Trace-Id"] = request.state.trace_id
        return response
