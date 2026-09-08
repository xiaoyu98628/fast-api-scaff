"""定义 SQL 失败任务表的 ORM 映射。"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, LargeBinary, String
from sqlalchemy.dialects.mysql import LONGBLOB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.orm.main import MainBase


class FailedJobModel(MainBase):
    """持久化失败分类和可用于重放的原始消息信封。"""

    __tablename__ = "queue_failed_jobs"
    __table_args__ = {"comment": "队列失败任务记录"}

    failure_id: Mapped[str] = mapped_column(String(36), primary_key=True, comment="失败记录 ID")
    job_id: Mapped[str | None] = mapped_column(String(36), comment="原任务 ID，非法信封时为空")
    payload: Mapped[bytes] = mapped_column(LargeBinary().with_variant(LONGBLOB(), "mysql"), comment="原始任务信封")
    connection: Mapped[str] = mapped_column(String(200), comment="队列连接名")
    queue: Mapped[str] = mapped_column(String(200), comment="逻辑队列名")
    failed_at: Mapped[datetime] = mapped_column(DateTime(), index=True, comment="最终失败时间")
    attempts: Mapped[int] = mapped_column(Integer(), comment="本次投递执行次数")
    reason: Mapped[str] = mapped_column(String(200), comment="失败原因分类")
