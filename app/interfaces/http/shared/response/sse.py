"""定义项目统一的单条 SSE 事件类型。"""

from fastapi.sse import ServerSentEvent


class SseResponse(ServerSentEvent):
    """单条 SSE 事件，字段与编码语义沿用 FastAPI，不代表整个 HTTP 流。"""
