"""提供 Scheduler 测试使用的最小假实现。"""

import asyncio
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from app.interfaces.scheduler.contracts import JobDispatcher, QueueJobSchedule


@dataclass(slots=True)
class FakeSchedulerEngine:
    """记录宿主调用顺序且不创建后台任务。"""

    events: list[str] = field(default_factory=list)
    definitions: tuple[QueueJobSchedule, ...] = ()
    dispatcher: JobDispatcher | None = None

    async def start(
        self,
        definitions: tuple[QueueJobSchedule, ...],
        dispatcher: JobDispatcher,
    ) -> None:
        """保存启动参数。"""

        self.events.append("start")
        self.definitions = definitions
        self.dispatcher = dispatcher

    async def wait(self, stop: asyncio.Event) -> None:
        """等待测试发出停止信号。"""

        self.events.append("wait")
        await stop.wait()

    async def aclose(self) -> None:
        """记录关闭事件。"""

        self.events.append("close")


@dataclass(slots=True)
class FakeDispatcher:
    """记录 Scheduler 投递的任务和路由。"""

    calls: list[tuple[object, str | None, str | None]] = field(default_factory=list)
    job_id: UUID = field(default_factory=uuid4)

    async def __call__(
        self,
        job: object,
        *,
        connection: str | None = None,
        queue: str | None = None,
        correlation_id: str | None = None,
    ) -> UUID:
        """保存调用并返回固定消息 ID。"""

        assert correlation_id is None
        self.calls.append((job, connection, queue))
        return self.job_id
