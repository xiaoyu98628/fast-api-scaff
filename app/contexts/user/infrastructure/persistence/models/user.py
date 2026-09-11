"""定义用户聚合在主数据库中的 SQLAlchemy 模型。"""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.orm.main import MainBase


class UserModel(MainBase):
    """用户聚合的数据库持久化模型。"""

    __tablename__ = "users"
    # 数据库约束是并发写入下的最终防线，应用层预检查只负责友好反馈。
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
    version: Mapped[int] = mapped_column(Integer(), nullable=False, default=1, server_default=text("1"), comment="并发版本")
