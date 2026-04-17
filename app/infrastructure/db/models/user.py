from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import DateTime, String, func, CHAR, Index, UniqueConstraint

from app.application.enums.user_status import UserStatus
from app.infrastructure.db.base import Base


class User(Base):
    __tablename_suffix__ = "users"

    # 表备注
    # SQLAlchemy 要求：当 __table_args__ 为 tuple 时，dict（表参数）必须放在最后
    __table_args__ = (
        # 唯一索引
        UniqueConstraint('username', name='uq_username'),
        # 普通索引
        # Index('idx_username', 'username'),
        # 表注释
        {'comment': '用户表'},
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
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="删除时间")