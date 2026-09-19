"""定义 Scheduler 进程的稳定错误输出。"""

import logging
from collections.abc import Callable

import typer

from app.infrastructure.logging.record import log_extra, safe_exception_details
from app.infrastructure.queue.errors import QueueError
from app.interfaces.scheduler.errors import SchedulerError

type SchedulerEntrypoint = Callable[[], None]

_logger = logging.getLogger(__name__)


def run_scheduler(entrypoint: SchedulerEntrypoint) -> None:
    """执行 Scheduler，并把公开错误转换成稳定的非零退出。"""

    try:
        entrypoint()
    except (QueueError, SchedulerError) as error:
        _log_scheduler_failure(error)
        typer.echo(str(error), err=True)
        raise SystemExit(1) from None
    except Exception as error:
        _log_scheduler_failure(error)
        typer.echo(f"Scheduler 运行失败：{type(error).__name__}。", err=True)
        raise SystemExit(1) from None


def _log_scheduler_failure(error: BaseException) -> None:
    """记录不包含异常消息和运行时局部变量的 Scheduler 失败诊断。"""

    error_type, stacktrace = safe_exception_details(error)
    _logger.error(
        "Scheduler execution failed",
        extra=log_extra("scheduler.failed", error_type=error_type, stacktrace=stacktrace),
    )
