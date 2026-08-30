from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.orm.main import MainBase


class UserRecord(MainBase):
    """用户聚合的数据库持久化模型。"""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username"),
        UniqueConstraint("email"),
        CheckConstraint("status IN ('active', 'disabled')", name="status"),
        {"comment": "用户信息"},
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, comment="用户 ID")
    username: Mapped[str] = mapped_column(String(32), nullable=False, comment="用户名")
    email: Mapped[str] = mapped_column(String(254), nullable=False, comment="邮箱地址")
    display_name: Mapped[str] = mapped_column(String(80), nullable=False, comment="显示名称")
    status: Mapped[str] = mapped_column(String(16), nullable=False, comment="用户状态")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="更新时间")
