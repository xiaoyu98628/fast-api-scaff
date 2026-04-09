"""请求访问日志中间件：记录方法、路径、状态码与耗时。"""

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("app.request")


class RequestLogMiddleware(BaseHTTPMiddleware):
    """记录每个请求的访问日志。"""

    async def dispatch(self, request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - started) * 1000

        trace_id = getattr(request.state, "trace_id", "-")
        extra = {"trace_id": trace_id}
        logger.info(
            "%s %s -> %s (%.2f ms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            extra=extra,
        )
        return response
