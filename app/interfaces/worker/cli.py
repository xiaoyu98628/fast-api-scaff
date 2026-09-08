"""定义 Worker 命令行参数和稳定的进程错误输出。"""

from collections.abc import Callable
from typing import Protocol

import typer

from app.infrastructure.queue.errors import QueueError


class WorkerOperation(Protocol):
    """Worker CLI 调用的同步宿主入口。"""

    def __call__(self, *, connection: str | None, queue: str | None, concurrency: int | None) -> None: ...


type WorkerEntrypoint = Callable[[], None]


def create_worker(operation: WorkerOperation) -> typer.Typer:
    """创建只负责参数解析、不承担资源装配的 Typer 应用。"""

    application = typer.Typer(pretty_exceptions_enable=False)

    @application.command()
    def work(
        connection: str | None = typer.Option(None),
        queue: str | None = typer.Option(None),
        concurrency: int | None = typer.Option(None, min=1, max=1024),
    ) -> None:
        """消费并执行队列中的后台任务。"""
        operation(connection=connection, queue=queue, concurrency=concurrency)

    return application


def run_worker(entrypoint: WorkerEntrypoint) -> None:
    """执行 Worker，并把公开错误转换成稳定的非零退出。"""

    try:
        entrypoint()
    except QueueError as error:
        typer.echo(str(error), err=True)
        raise SystemExit(1) from None
    except Exception as error:
        typer.echo(f"Worker 运行失败：{type(error).__name__}；未确认任务将由后端恢复。", err=True)
        raise SystemExit(1) from None
