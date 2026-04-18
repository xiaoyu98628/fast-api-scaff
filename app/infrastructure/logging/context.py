"""请求级日志上下文：用于在任意日志点注入 trace_id。"""

from contextvars import ContextVar

_trace_id_ctx: ContextVar[str] = ContextVar("trace_id", default="-")


def set_trace_id(trace_id: str) -> None:
    _trace_id_ctx.set(trace_id)


def get_trace_id() -> str:
    return _trace_id_ctx.get()
