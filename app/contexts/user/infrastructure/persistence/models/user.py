from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.orm.main import MainBase


class UserModel(MainBase):
    """用户聚合的数据库持久化模型。"""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username"),
        UniqueConstraint("email"),
        CheckConstraint("status IN ('active', 'disabled')", name="status"),
        {"comment": "用户信息"},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, comment="用户 ID")
    username: Mapped[str] = mapped_column(String(32), nullable=False, comment="用户名")
    email: Mapped[str] = mapped_column(String(254), nullable=False, comment="邮箱地址")
    password: Mapped[str] = mapped_column(String(255), nullable=False, comment="密码哈希")
    status: Mapped[str] = mapped_column(String(16), nullable=False, comment="用户状态")
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, comment="更新时间")
