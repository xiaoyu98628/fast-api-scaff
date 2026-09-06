from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.orm.main import MainBase


class UserSessionModel(MainBase):
    __tablename__ = "user_sessions"
    __table_args__ = (
        CheckConstraint("expires_at > issued_at", name="time_range"),
        {"comment": "用户登录会话"},
    )

    token_digest: Mapped[str] = mapped_column(String(64), primary_key=True, comment="令牌 SHA-256 摘要")
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="用户 ID")
    issued_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, comment="签发时间")
    expires_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, index=True, comment="过期时间")
