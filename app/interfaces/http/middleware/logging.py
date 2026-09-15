"""定义 HTTP 入站中间件使用的稳定结构化日志事件。"""

from enum import StrEnum


class HttpLogEvent(StrEnum):
    """区分请求校验、访问完成和请求链路失败事件。"""

    INVALID_REQUEST_ID = "http.request.invalid_request_id"
    REQUEST_COMPLETED = "http.request.completed"
    SSE_STREAM_FAILED = "http.sse.stream_failed"
    UNHANDLED_EXCEPTION = "http.request.unhandled_exception"
