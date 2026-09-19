"""定义代码计划、触发规则和队列投递契约。"""

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from app.infrastructure.queue.job import encode_job

_SCHEDULE_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}")

type CronField = int | str
type ScheduleTrigger = CronSchedule | IntervalSchedule


class CoalescePolicy(StrEnum):
    """定义多个错过触发时间的合并方式。"""

    LATEST = "latest"
    ALL = "all"


class IntervalStartPolicy(StrEnum):
    """定义固定间隔计划的首次触发方式。"""

    IMMEDIATELY = "immediately"
    AFTER_INTERVAL = "after_interval"


@dataclass(frozen=True, slots=True)
class CronSchedule:
    """按照 Scheduler 进程本地时间描述 Cron 计划。"""

    second: CronField = 0
    minute: CronField = 0
    hour: CronField = "*"
    day: CronField = "*"
    month: CronField = "*"
    day_of_week: str = "*"

    def __post_init__(self) -> None:
        """拒绝在 APScheduler 版本间语义不同的数字星期。"""

        if not self.day_of_week.strip() or any(character.isdigit() for character in self.day_of_week):
            raise ValueError("day_of_week 必须使用 mon–sun 英文名称，不能使用数字")


@dataclass(frozen=True, slots=True)
class IntervalSchedule:
    """描述固定秒数间隔和明确的首次触发方式。"""

    seconds: int
    start: IntervalStartPolicy = IntervalStartPolicy.AFTER_INTERVAL

    def __post_init__(self) -> None:
        """拒绝 bool、浮点数和非正执行间隔。"""

        if type(self.seconds) is not int or self.seconds <= 0:
            raise ValueError("定时间隔必须是正整数秒")


@dataclass(frozen=True, slots=True)
class QueueJobSchedule:
    """描述一个到期后投递到现有队列的不可变任务计划。"""

    id: str
    trigger: ScheduleTrigger
    job: object
    connection: str | None = None
    queue: str | None = None
    coalesce: CoalescePolicy = CoalescePolicy.LATEST
    misfire_grace_seconds: int = 300

    def __post_init__(self) -> None:
        """校验稳定标识、执行参数和可编码 QueueJob。"""

        if _SCHEDULE_ID_PATTERN.fullmatch(self.id) is None:
            raise ValueError("定时计划 ID 不合法")
        if not isinstance(self.trigger, CronSchedule | IntervalSchedule):
            raise TypeError("定时计划 Trigger 不合法")
        if not isinstance(self.coalesce, CoalescePolicy):
            raise TypeError("定时计划合并策略不合法")
        if type(self.misfire_grace_seconds) is not int or self.misfire_grace_seconds <= 0:
            raise ValueError("misfire_grace_seconds 必须是正整数")

        # 启动阶段验证任务定义和 payload，避免等到计划触发时才暴露部署错误。
        encode_job(self.job)


class JobDispatcher(Protocol):
    """描述 Scheduler 使用的队列公共投递入口。"""

    async def __call__(
        self,
        job: object,
        *,
        connection: str | None = None,
        queue: str | None = None,
        correlation_id: str | None = None,
    ) -> UUID:
        """投递 QueueJob，并返回新消息的稳定 ID。"""

        ...
