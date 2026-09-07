from datetime import datetime

from sqlalchemy import DateTime, Integer, LargeBinary, String
from sqlalchemy.dialects.mysql import LONGBLOB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.orm.main import MainBase


class FailedJobModel(MainBase):
    __tablename__ = "queue_failed_jobs"
    failure_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str | None] = mapped_column(String(36))
    payload: Mapped[bytes] = mapped_column(LargeBinary().with_variant(LONGBLOB(), "mysql"))
    connection: Mapped[str] = mapped_column(String(200))
    queue: Mapped[str] = mapped_column(String(200))
    failed_at: Mapped[datetime] = mapped_column(DateTime(), index=True)
    attempts: Mapped[int] = mapped_column(Integer())
    reason: Mapped[str] = mapped_column(String(200))
