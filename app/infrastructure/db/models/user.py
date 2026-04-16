from datetime import datetime
from typing import Optional

from sqlalchemy.orm import declared_attr, Mapped, mapped_column
from sqlalchemy import DateTime, Integer, String, func, JSON, CHAR, Index, UniqueConstraint

from app.infrastructure.db.base import Base
from config.config import get_config

class User(Base):

    @declared_attr.directive
    def __tablename__(cls):
        config = get_config()
        return f"{config.database.prefix}users"

    # 表备注
    # SQLAlchemy 要求：当 __table_args__ 为 tuple 时，dict（表参数）必须放在最后
    __table_args__ = (
        UniqueConstraint('username', name='uq_username'),
        # Index('idx_username', 'username'),
        {'comment': '用户表'},
    )

    id: Mapped[str] = mapped_column(CHAR(26), nullable=False, primary_key=True, comment="编号")
    username: Mapped[str] = mapped_column(String(64), nullable=False, comment="用户名")
    password: Mapped[str] = mapped_column(String(128), nullable=False, comment="密码")
    nickname: Mapped[str] = mapped_column(String(64), nullable=False, comment="昵称")
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="删除时间")