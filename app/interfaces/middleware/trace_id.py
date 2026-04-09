"""为每个请求注入或透传 ``X-Trace-Id``，便于日志关联。"""

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class TraceIdMiddleware(BaseHTTPMiddleware):
    """为每个请求注入 trace id。"""

    trace_id_header = "X-Trace-Id"

    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get(self.trace_id_header)
        if not trace_id:
            trace_id = str(uuid.uuid4())

        request.state.trace_id = trace_id

        response = await call_next(request)
        response.headers[self.trace_id_header] = trace_id
        return response
