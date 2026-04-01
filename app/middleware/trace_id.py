import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

class TraceIdMiddleware(BaseHTTPMiddleware):
    """
    TraceId 中间件

    功能：
    1. 从请求头获取已有的 TraceId（如网关传递）
    2. 如果没有则生成新的 TraceId
    3. 将 TraceId 添加到响应头
    """

    TRACE_ID_HEADER = "X-Trace-Id"

    async def dispatch(self, request: Request, call_next):
        # 获取或生成 TraceId
        trace_id = request.headers.get(self.TRACE_ID_HEADER)
        if not trace_id:
            trace_id = str(uuid.uuid4())

        request.state.trace_id = trace_id

        response = await call_next(request)

        response.headers[self.TRACE_ID_HEADER] = trace_id

        return response