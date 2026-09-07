import builtins
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class FailedJobRecord:
    failure_id: UUID
    payload: bytes
    connection: str
    queue: str
    failed_at: datetime
    attempts: int
    reason: str
    job_id: UUID | None = None


class FailedJobStore(Protocol):
    async def save(self, record: FailedJobRecord) -> None: ...
    async def find(self, failure_id: UUID) -> FailedJobRecord | None: ...
    async def list(self, *, limit: int = 20, offset: int = 0) -> builtins.list[FailedJobRecord]: ...
    async def delete(self, failure_id: UUID) -> None: ...
