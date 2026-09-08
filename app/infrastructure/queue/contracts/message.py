"""定义驱动之间共享的版本化任务消息信封。"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class MessageEnvelope:
    """封装任务类型、业务 payload、追踪信息和重放来源。"""

    job_id: UUID
    job_type: str
    job_version: int
    payload: bytes
    enqueued_at: datetime
    correlation_id: str | None = None
    replay_of: UUID | None = None
