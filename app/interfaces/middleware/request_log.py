"""请求访问日志中间件：记录方法、路径、状态码与耗时。"""

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.common.utils.logger import log_info


class RequestLogMiddleware(BaseHTTPMiddleware):
    """记录每个请求的访问日志。"""

    async def dispatch(self, request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - started) * 1000

        trace_id = getattr(request.state, "trace_id", "-")
        log_info(
            "%s %s -> %s (%.2f ms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            channel="request",
            trace_id=trace_id,
        )
        return response
