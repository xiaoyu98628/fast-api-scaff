"""提供查询、重放和删除失败队列记录的 Console 命令。"""

from functools import partial
from uuid import UUID

import typer

from app.infrastructure.queue.job import job_type_path
from app.interfaces.console.command import ConsoleCommand
from app.interfaces.console.context import ConsoleContext
from app.interfaces.worker.discovery import discover_job_types
from app.interfaces.worker.resolver import JobResolver


def list_jobs() -> list[dict[str, object]]:
    """返回启动期会发现的任务契约和执行策略摘要。"""

    resolver = JobResolver(discover_job_types())
    return [
        {
            "reference": descriptor.reference,
            "type_path": job_type_path(descriptor.job_type),
            "version": descriptor.version,
            "supported_versions": tuple(sorted((descriptor.version, *descriptor.legacy_decoders))),
            "legacy_references": descriptor.legacy_references,
            "max_attempts": descriptor.policy.max_attempts,
            "backoff_seconds": descriptor.policy.backoff_seconds,
            "timeout_seconds": descriptor.policy.timeout_seconds,
        }
        for descriptor in resolver.descriptors
    ]


async def list_failures(context: ConsoleContext, *, limit: int, offset: int) -> list[dict[str, object]]:
    """分页返回失败任务元数据，不暴露原始消息载荷。"""

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
            "error_type": item.error_type,
            "stacktrace": item.stacktrace,
        }
        for item in records
    ]


async def replay_failure(context: ConsoleContext, *, failure_id: UUID) -> dict[str, UUID]:
    """重新发布失败任务，并返回新任务与来源记录的 ID。"""

    job_id = await context.container.queues.replay(failure_id)
    return {"job_id": job_id, "replay_of": failure_id}


async def forget_failure(context: ConsoleContext, *, failure_id: UUID) -> dict[str, UUID]:
    """删除一条失败记录并返回被删除的 ID。"""

    await context.container.queues.failed_jobs.delete(failure_id)
    return {"failure_id": failure_id}


class FailedQueueConsoleCommand(ConsoleCommand):
    """注册并处理 ``queue failed`` 查询命令。"""

    group = "queue"
    group_help = "查看队列任务并管理持久失败记录。"
    name = "failed"
    help = "查询失败任务元数据，不输出任务数据。"

    def handle(self, limit: int = typer.Option(20, min=1, max=1000), offset: int = typer.Option(0, min=0)) -> None:
        """校验分页参数并输出失败记录列表。"""

        result = self._console.run(partial(list_failures, limit=limit, offset=offset))
        self._console.presenter.result(result)


class RetryQueueConsoleCommand(ConsoleCommand):
    """注册并处理 ``queue retry`` 重放命令。"""

    group = "queue"
    group_help = "查看队列任务并管理持久失败记录。"
    name = "retry"
    help = "重放失败记录并保留原记录；结果不确定时不要盲目重复执行。"

    def handle(self, failure_id: UUID) -> None:
        """重放指定失败记录并输出新任务 ID。"""

        self._console.presenter.result(self._console.run(partial(replay_failure, failure_id=failure_id)))


class ForgetQueueConsoleCommand(ConsoleCommand):
    """注册并处理 ``queue forget`` 删除命令。"""

    group = "queue"
    group_help = "查看队列任务并管理持久失败记录。"
    name = "forget"
    help = "删除指定失败记录。"

    def handle(self, failure_id: UUID) -> None:
        """删除指定失败记录并输出其 ID。"""

        self._console.presenter.result(self._console.run(partial(forget_failure, failure_id=failure_id)))


class ListQueueJobsConsoleCommand(ConsoleCommand):
    """注册并处理 ``queue jobs`` 任务目录查询命令。"""

    group = "queue"
    group_help = "查看队列任务并管理持久失败记录。"
    name = "jobs"
    help = "列出 Worker 启动时会发现的任务契约。"

    def handle(self) -> None:
        """发现并校验任务后输出不含业务数据的契约摘要。"""

        self._console.presenter.result(list_jobs())
