"""提供查看代码定时计划的 Console 命令。"""

from app.infrastructure.queue.job import encode_job
from app.interfaces.console.command import ConsoleCommand
from app.interfaces.scheduler.contracts import CronSchedule, IntervalSchedule, ScheduleTrigger
from app.interfaces.scheduler.discovery import discover_schedule_registry


def list_schedules() -> list[dict[str, object]]:
    """发现代码计划并返回不包含任务 payload 的摘要。"""

    definitions = discover_schedule_registry().definitions
    result: list[dict[str, object]] = []
    for definition in definitions:
        encoded_job = encode_job(definition.job)
        result.append(
            {
                "id": definition.id,
                "trigger": _trigger_summary(definition.trigger),
                "job": {
                    "reference": encoded_job.job_type,
                    "version": encoded_job.version,
                },
                "connection": definition.connection,
                "queue": definition.queue,
                "coalesce": definition.coalesce,
                "misfire_grace_seconds": definition.misfire_grace_seconds,
            }
        )
    return result


def _trigger_summary(trigger: ScheduleTrigger) -> dict[str, object]:
    """把项目 Trigger 转换为稳定且不依赖 APScheduler 的输出。"""

    match trigger:
        case CronSchedule():
            return {
                "type": "cron",
                "second": trigger.second,
                "minute": trigger.minute,
                "hour": trigger.hour,
                "day": trigger.day,
                "month": trigger.month,
                "day_of_week": trigger.day_of_week,
            }
        case IntervalSchedule():
            return {
                "type": "interval",
                "seconds": trigger.seconds,
                "start": trigger.start,
            }


class ListSchedulerConsoleCommand(ConsoleCommand):
    """注册并处理 ``scheduler list`` 计划目录查询命令。"""

    group = "scheduler"
    group_help = "查看代码定时计划。"
    name = "list"
    help = "列出当前部署声明的定时计划。"

    def handle(self) -> None:
        """构建计划目录并输出不含任务数据的摘要。"""

        self._console.presenter.result(list_schedules())
