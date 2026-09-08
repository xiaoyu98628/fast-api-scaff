"""定义失败任务记录及其持久化契约。"""

import builtins
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class FailedJobRecord:
    """保存失败分类和后端交付的完整原始信封。"""

    failure_id: UUID
    payload: bytes
    connection: str
    queue: str
    failed_at: datetime
    attempts: int
    reason: str
    job_id: UUID | None = None


class FailedJobStore(Protocol):
    """提供失败任务的幂等保存、查询和删除能力。"""

    async def save(self, record: FailedJobRecord) -> None: ...
    async def find(self, failure_id: UUID) -> FailedJobRecord | None: ...
    async def list(self, *, limit: int = 20, offset: int = 0) -> builtins.list[FailedJobRecord]: ...
    async def delete(self, failure_id: UUID) -> None: ...
