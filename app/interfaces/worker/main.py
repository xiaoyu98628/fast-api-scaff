import typer

from app.infrastructure.queue.errors import QueueError
from app.interfaces.worker.application import WorkerApplication

app = typer.Typer(pretty_exceptions_enable=False)


@app.command()
def work(
    connection: str | None = typer.Option(None), queue: str | None = typer.Option(None), concurrency: int | None = typer.Option(None, min=1, max=1024)
) -> None:
    """独立执行已注册的后台任务。"""
    WorkerApplication().run(connection=connection, queue=queue, concurrency=concurrency)


def main() -> None:
    try:
        app()
    except QueueError as error:
        typer.echo(str(error), err=True)
        raise SystemExit(1) from None
    except Exception as error:
        typer.echo(f"Worker 运行失败：{type(error).__name__}；未确认任务将由后端恢复。", err=True)
        raise SystemExit(1) from None
