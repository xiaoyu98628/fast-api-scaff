"""用户表数据访问。"""

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models.user import User


class UserRepository:
    """用户仓储：仅封装数据访问，不含业务规则与事务提交。"""

    @staticmethod
    async def get_active_by_username(session: AsyncSession, username: str) -> User | None:
        """按用户名查询未软删用户；不存在则返回 ``None``。"""
        stmt = select(User).where(
            User.username == username,
            User.deleted_at.is_(None),
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def show(session: AsyncSession, user_id: str) -> User | None:
        """按主键查询未软删用户（详情）。"""
        stmt = select(User).where(User.id == user_id, User.deleted_at.is_(None))
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def store(
        session: AsyncSession,
        *,
        user_id: str,
        username: str,
        password_hash: str,
        nickname: str,
    ) -> User:
        """新增用户行（ORM 构造仅在仓储内完成）。"""
        user = User(
            id=user_id,
            username=username,
            password=password_hash,
            nickname=nickname,
        )
        session.add(user)
        await session.flush()
        return user

    @staticmethod
    async def update(
        session: AsyncSession,
        user_id: str,
        *,
        nickname: str | None = None,
        password_hash: str | None = None,
    ) -> User | None:
        """按主键更新未软删用户；不存在则返回 ``None``。"""
        user = await UserRepository.show(session, user_id)
        if user is None:
            return None
        if nickname is not None:
            user.nickname = nickname
        if password_hash is not None:
            user.password = password_hash
        await session.flush()
        return user

    @staticmethod
    async def destroy(session: AsyncSession, user_id: str) -> bool:
        """软删除；成功更新至少一行返回 ``True``。"""
        stmt = (
            update(User)
            .where(User.id == user_id, User.deleted_at.is_(None))
            .values(deleted_at=datetime.now(UTC))
        )
        result = await session.execute(stmt)
        return result.rowcount > 0
