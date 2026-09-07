from functools import partial
from uuid import UUID

import typer

from app.infrastructure.queue.errors import QueueError
from app.interfaces.console.command import ConsoleCommand
from app.interfaces.console.context import ConsoleContext


def require_persistent_store(context: ConsoleContext) -> None:
    if not context.container.queues.persistent_failures:
        raise QueueError("独立 Console 无法读取 Worker 内存记录；请配置 QUEUE_FAILED__DRIVER=sql 并执行迁移")


async def list_failures(context: ConsoleContext, *, limit: int, offset: int) -> list[dict[str, object]]:
    require_persistent_store(context)
    records = await context.container.queues.failed_jobs.list(limit=limit, offset=offset)
    return [
        {
            "failure_id": item.failure_id,
            "job_id": item.job_id,
            "connection": item.connection,
            "queue": item.queue,
            "failed_at": item.failed_at,
            "attempts": item.attempts,
            "reason": item.reason,
        }
        for item in records
    ]


async def replay_failure(context: ConsoleContext, *, failure_id: UUID) -> dict[str, UUID]:
    require_persistent_store(context)
    job_id = await context.container.queues.replay(failure_id)
    return {"job_id": job_id, "replay_of": failure_id}


async def forget_failure(context: ConsoleContext, *, failure_id: UUID) -> dict[str, UUID]:
    require_persistent_store(context)
    await context.container.queues.failed_jobs.delete(failure_id)
    return {"failure_id": failure_id}


class FailedQueueConsoleCommand(ConsoleCommand):
    group = "queue"
    group_help = "管理持久失败任务。"
    name = "failed"
    help = "查询失败任务元数据，不输出任务数据。"

    def handle(self, limit: int = typer.Option(20, min=1, max=1000), offset: int = typer.Option(0, min=0)) -> None:
        result = self._console.run(partial(list_failures, limit=limit, offset=offset))
        self._console.presenter.result(result)


class RetryQueueConsoleCommand(ConsoleCommand):
    group = "queue"
    group_help = "管理持久失败任务。"
    name = "retry"
    help = "重放失败记录并保留原记录；结果不确定时不要盲目重复执行。"

    def handle(self, failure_id: UUID) -> None:
        self._console.presenter.result(self._console.run(partial(replay_failure, failure_id=failure_id)))


class ForgetQueueConsoleCommand(ConsoleCommand):
    group = "queue"
    group_help = "管理持久失败任务。"
    name = "forget"
    help = "删除指定失败记录。"

    def handle(self, failure_id: UUID) -> None:
        self._console.presenter.result(self._console.run(partial(forget_failure, failure_id=failure_id)))
