from datetime import datetime

from sqlalchemy import CHAR, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.user.enums import UserStatus
from app.infrastructure.database.orm.base import Base


class User(Base):
    __table_name__ = "users"

    id: Mapped[str] = mapped_column(CHAR(26), primary_key=True, comment="编号（ULID）")
    username: Mapped[str] = mapped_column(String(64), nullable=False, comment="用户名")
    password: Mapped[str] = mapped_column(String(128), nullable=False, comment="密码")
    nickname: Mapped[str] = mapped_column(String(64), nullable=False, comment="昵称")
    status: Mapped[str] = mapped_column(
        String(16),
        default=UserStatus.ACTIVATION.value,
        server_default=UserStatus.ACTIVATION.value,
        comment="状态[activation:激活,locking:locking]",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        comment="创建时间",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="删除时间")
