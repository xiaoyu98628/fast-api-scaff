"""定义失败任务记录及其持久化契约。"""

import builtins
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.infrastructure.logging.record import ExceptionStackFrame


@dataclass(frozen=True, slots=True)
class FailedJobRecord:
    """保存失败分类、安全诊断和后端交付的完整原始信封。"""

    failure_id: UUID
    payload: bytes
    connection: str
    queue: str
    failed_at: datetime
    attempts: int
    reason: str
    job_id: UUID | None = None
    error_type: str | None = None
    stacktrace: tuple[ExceptionStackFrame, ...] = ()


class FailedJobStore(Protocol):
    """提供失败任务的幂等保存、查询和删除能力。"""

    async def save(self, record: FailedJobRecord) -> None:
        """按 failure_id 幂等保存完整失败记录。"""

        ...

    async def find(self, failure_id: UUID) -> FailedJobRecord | None:
        """按 ID 查找失败记录，不存在时返回 None。"""

        ...

    async def list(self, *, limit: int = 20, offset: int = 0) -> builtins.list[FailedJobRecord]:
        """按存储实现约定的稳定顺序分页返回失败记录。"""

        ...

    async def delete(self, failure_id: UUID) -> None:
        """幂等删除失败记录。"""

        ...
