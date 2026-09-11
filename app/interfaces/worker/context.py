"""定义 Worker 进程上下文和单条队列任务的执行上下文。"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.config.settings import Settings
from app.runtime.container import ApplicationContainer


@dataclass(frozen=True, slots=True)
class WorkerContext:
    """保存队列任务执行期间可使用的配置和应用容器。"""

    settings: Settings
    container: ApplicationContainer


@dataclass(frozen=True, slots=True)
class JobMetadata:
    """描述当前队列消息及其投递来源。"""

    id: UUID
    reference: str
    version: int
    enqueued_at: datetime
    queue_connection: str
    queue_name: str
    correlation_id: str | None = None
    replay_of: UUID | None = None


@dataclass(frozen=True, slots=True)
class JobExecutionContext:
    """提供单条队列任务所需的应用能力和消息元数据。"""

    settings: Settings
    container: ApplicationContainer
    job: JobMetadata
