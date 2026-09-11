"""把当前 HTTP、Console 或队列任务上下文补充到 LogRecord。"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from starlette_context import context
from starlette_context.header_keys import HeaderKeys


@dataclass(frozen=True, slots=True)
class JobLogContext:
    """保存允许自动附加到日志的非敏感任务标识。"""

    job_id: str
    job_type: str
    job_version: int
    queue_connection: str
    queue_name: str
    correlation_id: str | None = None
    replay_of: str | None = None


_JOB_LOG_CONTEXT: ContextVar[JobLogContext | None] = ContextVar("job_log_context", default=None)
_CONSOLE_COMMAND_ID: ContextVar[str | None] = ContextVar("console_command_id", default=None)


@contextmanager
def bind_console_log_context(command_id: str) -> Iterator[None]:
    """在当前执行流内绑定 Console 命令 ID，并在退出时恢复原值。"""

    token = _CONSOLE_COMMAND_ID.set(command_id)
    try:
        yield
    finally:
        _CONSOLE_COMMAND_ID.reset(token)


def current_console_command_id() -> str | None:
    """返回当前 Console 命令 ID；不在命令作用域时返回 None。"""

    return _CONSOLE_COMMAND_ID.get()


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

        # 显式传入的 request_id 优先，避免覆盖后台任务等调用方提供的上下文。
        if getattr(record, "request_id", None) is None:
            setattr(record, "request_id", _get_request_id())

        command_id = current_console_command_id()
        if command_id is not None and getattr(record, "command_id", None) is None:
            setattr(record, "command_id", command_id)

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
        "correlation_id",
        "replay_of",
    ):
        value = getattr(job_context, field)
        if value is not None and getattr(record, field, None) is None:
            setattr(record, field, value)


def _get_request_id() -> str | None:
    """安全读取当前 Starlette 上下文中的请求标识。"""

    # 启动期、后台任务和 Console 都可能在 HTTP 请求之外记录日志。
    if not context.exists():
        return None

    try:
        return str(context[HeaderKeys.request_id])
    except KeyError, RuntimeError:
        return None
