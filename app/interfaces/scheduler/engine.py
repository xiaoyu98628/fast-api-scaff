"""定义 SchedulerHost 依赖的调度引擎边界。"""

import asyncio
from typing import Protocol

from app.interfaces.scheduler.contracts import JobDispatcher, QueueJobSchedule


class SchedulerEngine(Protocol):
    """管理计划注册、触发循环和调度资源生命周期。"""

    async def start(
        self,
        definitions: tuple[QueueJobSchedule, ...],
        dispatcher: JobDispatcher,
    ) -> None:
        """注册全部计划并启动触发循环。"""

        ...

    async def wait(self, stop: asyncio.Event) -> None:
        """等待宿主停止请求或调度引擎失败。"""

        ...

    async def aclose(self) -> None:
        """停止产生新任务并释放调度资源。"""

        ...
