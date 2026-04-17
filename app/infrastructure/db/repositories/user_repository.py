"""用户表数据访问。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models.user import User


class UserRepository:
    """用户仓储：仅封装查询，不含业务规则。"""

    @staticmethod
    async def get_active_by_username(session: AsyncSession, username: str) -> User | None:
        """按用户名查询未软删用户；不存在则返回 ``None``。"""
        stmt = select(User).where(
            User.username == username,
            User.deleted_at.is_(None),
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
