import builtins
from uuid import UUID

from app.infrastructure.queue.contracts.failed_store import FailedJobRecord


class MemoryFailedJobStore:
    def __init__(self) -> None:
        self._records: dict[UUID, FailedJobRecord] = {}

    async def save(self, record: FailedJobRecord) -> None:
        self._records.setdefault(record.failure_id, record)

    async def find(self, failure_id: UUID) -> FailedJobRecord | None:
        return self._records.get(failure_id)

    async def list(self, *, limit: int = 20, offset: int = 0) -> builtins.list[FailedJobRecord]:
        if limit < 1 or offset < 0:
            raise ValueError("分页参数不合法")
        records = sorted(self._records.values(), key=lambda item: (item.failed_at, item.failure_id), reverse=True)
        return records[offset : offset + limit]

    async def delete(self, failure_id: UUID) -> None:
        self._records.pop(failure_id, None)
