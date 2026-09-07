import builtins
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.infrastructure.database.manager import DatabaseManager
from app.infrastructure.queue.contracts.failed_store import FailedJobRecord
from app.infrastructure.queue.failed.sql.model import FailedJobModel


class SqlFailedJobStore:
    def __init__(self, databases: DatabaseManager, database: str = "main") -> None:
        self._databases = databases
        self._database = database

    async def save(self, record: FailedJobRecord) -> None:
        try:
            async with self._databases.session(self._database) as session:
                session.add(
                    FailedJobModel(
                        failure_id=str(record.failure_id),
                        job_id=str(record.job_id) if record.job_id else None,
                        payload=record.payload,
                        connection=record.connection,
                        queue=record.queue,
                        failed_at=record.failed_at,
                        attempts=record.attempts,
                        reason=record.reason,
                    )
                )
                await session.commit()
        except IntegrityError:
            if await self.find(record.failure_id) is None:
                raise

    async def find(self, failure_id: UUID) -> FailedJobRecord | None:
        async with self._databases.session(self._database) as session:
            row = await session.get(FailedJobModel, str(failure_id))
            return self._record(row) if row is not None else None

    async def list(self, *, limit: int = 20, offset: int = 0) -> builtins.list[FailedJobRecord]:
        if not 1 <= limit <= 1000 or offset < 0:
            raise ValueError("分页参数不合法")
        async with self._databases.session(self._database) as session:
            query = select(FailedJobModel).order_by(FailedJobModel.failed_at.desc(), FailedJobModel.failure_id.desc()).limit(limit).offset(offset)
            return [self._record(row) for row in (await session.scalars(query)).all()]

    async def delete(self, failure_id: UUID) -> None:
        async with self._databases.session(self._database) as session:
            await session.execute(delete(FailedJobModel).where(FailedJobModel.failure_id == str(failure_id)))
            await session.commit()

    @staticmethod
    def _record(row: FailedJobModel) -> FailedJobRecord:
        return FailedJobRecord(
            UUID(row.failure_id),
            row.payload,
            row.connection,
            row.queue,
            row.failed_at,
            row.attempts,
            row.reason,
            UUID(row.job_id) if row.job_id else None,
        )
