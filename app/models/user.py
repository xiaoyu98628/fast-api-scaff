from datetime import datetime
from typing import Optional

from sqlalchemy import CHAR, DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.enums.user_status import UserStatus
from app.models.base import Base


class User(Base):
    __tablename_suffix__ = "users"

    __table_args__ = (
        UniqueConstraint("username", name="uq_username"),
        {"comment": "用户表"},
    )

    id: Mapped[str] = mapped_column(CHAR(26), nullable=False, primary_key=True, comment="编号")
    username: Mapped[str] = mapped_column(String(64), nullable=False, comment="用户名")
    password: Mapped[str] = mapped_column(String(128), nullable=False, comment="密码")
    nickname: Mapped[str] = mapped_column(String(64), nullable=False, comment="昵称")
    status: Mapped[str] = mapped_column(
        String(16),
        default=UserStatus.ACTIVATION.value,
        server_default=UserStatus.ACTIVATION.value,
        comment="状态[activation:激活,locking:锁定]",
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="删除时间")
