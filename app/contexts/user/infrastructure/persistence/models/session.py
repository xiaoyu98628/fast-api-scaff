"""定义服务器端用户会话的 SQLAlchemy 模型。"""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.orm.main import MainBase


class UserSessionModel(MainBase):
    """保存令牌摘要、所属用户及会话有效时间。"""

    __tablename__ = "user_sessions"
    # 数据库再次约束时间范围，并通过外键级联清理被删除用户的会话。
    __table_args__ = (
        CheckConstraint("expires_at > issued_at", name="time_range"),
        {"comment": "用户登录会话"},
    )

    token_digest: Mapped[str] = mapped_column(String(64), primary_key=True, comment="令牌 SHA-256 摘要")
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="用户 ID")
    issued_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, comment="签发时间")
    expires_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, index=True, comment="过期时间")
