"""请求作用域 ContextVar：trace、Request、头快照、可选 extra。

清理使用 ``ContextVar.reset(token)``，避免 ``finally`` 里手工写占位值。
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar, Token
from typing import Any

from starlette.requests import Request

TRACE_ID_HEADER_DEFAULT = "X-Trace-Id"
_PLACEHOLDER_TRACE = "-"

_trace_id_ctx: ContextVar[str] = ContextVar("trace_id", default=_PLACEHOLDER_TRACE)
_request_ctx: ContextVar[Request | None] = ContextVar("request_scope_request", default=None)
_headers_ctx: ContextVar[dict[str, str] | None] = ContextVar("request_scope_headers", default=None)
_extra_ctx: ContextVar[dict[str, Any] | None] = ContextVar("request_scope_extra", default=None)


class RequestScopeTokens:
    """一次请求绑定产生的 reset token，仅供中间件 ``finally`` 使用。"""

    __slots__ = ("_items",)

    def __init__(self, items: list[tuple[ContextVar[Any], Token[Any]]]) -> None:
        self._items = items

    def reset_all(self) -> None:
        for var, tok in reversed(self._items):
            var.reset(tok)


def bind_request_scope(request: Request, *, trace_id_header: str = TRACE_ID_HEADER_DEFAULT) -> RequestScopeTokens:
    """绑定当前请求：生成 trace、写入 ``request.state``、填充 ContextVar。"""
    trace_id = request.headers.get(trace_id_header)
    if not trace_id:
        trace_id = str(uuid.uuid4())
    request.state.trace_id = trace_id

    items: list[tuple[ContextVar[Any], Token[Any]]] = [
        (_trace_id_ctx, _trace_id_ctx.set(trace_id)),
        (_request_ctx, _request_ctx.set(request)),
        (_headers_ctx, _headers_ctx.set(dict(request.headers))),
        (_extra_ctx, _extra_ctx.set({})),
    ]
    return RequestScopeTokens(items)


def get_trace_id() -> str:
    return _trace_id_ctx.get()


def set_trace_id(trace_id: str) -> None:
    """覆盖当前上下文 trace（兼容测试/少数手工场景；常规请求走 ``bind_request_scope``）。"""
    _trace_id_ctx.set(trace_id)


def trace_id_for_json(*, explicit: str | None = None) -> str | None:
    """对外 JSON：不显式输出占位 ``-``。"""
    tid = explicit if explicit is not None else get_trace_id()
    if tid == _PLACEHOLDER_TRACE or not tid:
        return None
    return tid


def get_current_request() -> Request | None:
    return _request_ctx.get()


def get_request_headers() -> dict[str, str]:
    headers = _headers_ctx.get()
    return dict(headers) if headers else {}


def get_header(key: str, default: str | None = None) -> str | None:
    key_lower = key.lower()
    for header_key, value in get_request_headers().items():
        if header_key.lower() == key_lower:
            return value
    return default


def set_scope_extra(key: str, value: Any) -> None:
    current = _extra_ctx.get()
    new_extra = dict(current) if current else {}
    new_extra[key] = value
    _extra_ctx.set(new_extra)


def get_scope_extra(key: str, default: Any = None) -> Any:
    extra = _extra_ctx.get()
    if not extra:
        return default
    return extra.get(key, default)
