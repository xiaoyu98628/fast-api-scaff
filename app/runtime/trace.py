"""生成并维护 HTTP、Console 与 Worker 共用的追踪标识和上下文。"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from uuid import uuid4

type TraceIdFactory = Callable[[], str]


def new_trace_id() -> str:
    """生成供各宿主入口共用的 UUID4 十六进制追踪标识。"""

    return uuid4().hex


@dataclass(frozen=True, slots=True)
class TraceContext:
    """保存当前执行流的跨宿主关联 ID 及来源宿主 ID。"""

    correlation_id: str | None = None
    request_id: str | None = None
    command_id: str | None = None


_TRACE_CONTEXT: ContextVar[TraceContext | None] = ContextVar("trace_context", default=None)


@contextmanager
def bind_trace_context(trace_context: TraceContext) -> Iterator[None]:
    """在当前执行流绑定追踪上下文，并在退出时恢复原值。"""

    token = _TRACE_CONTEXT.set(trace_context)
    try:
        yield
    finally:
        # 各宿主都可能并发复用线程或事件循环，必须按 token 恢复以避免串号。
        _TRACE_CONTEXT.reset(token)


def current_trace_context() -> TraceContext | None:
    """返回当前追踪上下文；不在宿主执行作用域时返回 None。"""

    return _TRACE_CONTEXT.get()


def current_correlation_id() -> str | None:
    """返回当前跨宿主关联 ID；没有已绑定上下文时返回 None。"""

    trace_context = current_trace_context()
    return trace_context.correlation_id if trace_context is not None else None
