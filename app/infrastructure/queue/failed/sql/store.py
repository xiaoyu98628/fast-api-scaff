"""使用独立短事务实现失败任务持久化。"""

import builtins
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.infrastructure.database.manager import DatabaseManager
from app.infrastructure.queue.contracts.failed_store import FailedJobRecord
from app.infrastructure.queue.failed.sql.model import FailedJobModel


class SqlFailedJobStore:
    """通过 DatabaseManager 访问指定数据库中的失败任务表。"""

    def __init__(self, databases: DatabaseManager, database: str = "main") -> None:
        self._databases = databases
        self._database = database

    async def save(self, record: FailedJobRecord) -> None:
        """幂等保存失败记录；相同 failure_id 已存在时视为成功。"""

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
            # failure_id 由消息身份确定；并发重复写入不应覆盖首次失败现场。
            if await self.find(record.failure_id) is None:
                raise

    async def find(self, failure_id: UUID) -> FailedJobRecord | None:
        """按失败记录 ID 查询，不延长业务事务生命周期。"""

        async with self._databases.session(self._database) as session:
            row = await session.get(FailedJobModel, str(failure_id))
            return self._record(row) if row is not None else None

    async def list(self, *, limit: int = 20, offset: int = 0) -> builtins.list[FailedJobRecord]:
        """按失败时间倒序分页返回记录。"""

        if not 1 <= limit <= 1000 or offset < 0:
            raise ValueError("分页参数不合法")
        async with self._databases.session(self._database) as session:
            query = select(FailedJobModel).order_by(FailedJobModel.failed_at.desc(), FailedJobModel.failure_id.desc()).limit(limit).offset(offset)
            return [self._record(row) for row in (await session.scalars(query)).all()]

    async def delete(self, failure_id: UUID) -> None:
        """幂等删除一条失败记录。"""

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
