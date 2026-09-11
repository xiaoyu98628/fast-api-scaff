"""把当前追踪或队列任务上下文补充到 LogRecord。"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from app.runtime.trace import TraceContext, current_trace_context


@dataclass(frozen=True, slots=True)
class JobLogContext:
    """保存允许自动附加到日志的非敏感任务标识。"""

    job_id: str
    job_type: str
    job_version: int
    queue_connection: str
    queue_name: str
    replay_of: str | None = None


_JOB_LOG_CONTEXT: ContextVar[JobLogContext | None] = ContextVar("job_log_context", default=None)


@contextmanager
def bind_job_log_context(job_context: JobLogContext) -> Iterator[None]:
    """在当前异步执行流内绑定任务日志字段，并在退出时恢复原值。"""

    token = _JOB_LOG_CONTEXT.set(job_context)
    try:
        yield
    finally:
        # Worker 并发槽共享线程和事件循环，必须按 token 恢复以避免任务间串号。
        _JOB_LOG_CONTEXT.reset(token)


class RuntimeContextFilter(logging.Filter):
    """在日志进入 Handler 时固化当前宿主执行上下文。"""

    def filter(self, record: logging.LogRecord) -> bool:
        """补充调用方未显式提供的关联字段，并允许日志继续输出。"""

        trace_context = current_trace_context()
        if trace_context is not None:
            _attach_trace_context(record, trace_context)

        job_context = _JOB_LOG_CONTEXT.get()
        if job_context is not None:
            _attach_job_context(record, job_context)

        return True


def _attach_job_context(record: logging.LogRecord, job_context: JobLogContext) -> None:
    """只补充非空且未由日志调用方显式指定的任务字段。"""

    for field in (
        "job_id",
        "job_type",
        "job_version",
        "queue_connection",
        "queue_name",
        "replay_of",
    ):
        value = getattr(job_context, field)
        if value is not None and getattr(record, field, None) is None:
            setattr(record, field, value)


def _attach_trace_context(record: logging.LogRecord, trace_context: TraceContext) -> None:
    """只补充非空且未由日志调用方显式指定的追踪字段。"""

    for field in ("request_id", "command_id", "correlation_id"):
        value = getattr(trace_context, field)
        if value is not None and getattr(record, field, None) is None:
            setattr(record, field, value)
