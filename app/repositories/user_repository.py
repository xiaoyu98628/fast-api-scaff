"""用户表数据访问。"""

from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums.user_status import UserStatus
from app.models.user import User


class UserRepository:
    """用户仓储：仅封装数据访问，不含业务规则与事务提交。"""

    @staticmethod
    async def get_active_by_username(session: AsyncSession, username: str) -> User | None:
        stmt = select(User).where(
            User.username == username,
            User.deleted_at.is_(None),
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def show(session: AsyncSession, user_id: str) -> User | None:
        stmt = select(User).where(User.id == user_id, User.deleted_at.is_(None))
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def count_not_deleted(session: AsyncSession) -> int:
        """未软删用户总数。"""
        stmt = select(func.count()).select_from(User).where(User.deleted_at.is_(None))
        result = await session.execute(stmt)
        return int(result.scalar_one())

    @staticmethod
    async def index(session: AsyncSession, *, offset: int, limit: int) -> list[User]:
        """分页列出未软删用户（按创建时间倒序）。"""
        stmt = (
            select(User)
            .where(User.deleted_at.is_(None))
            .order_by(User.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def store(
        session: AsyncSession,
        *,
        user_id: str,
        username: str,
        password_hash: str,
        nickname: str,
    ) -> User:
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
    async def update_status(
        session: AsyncSession,
        user_id: str,
        *,
        status: UserStatus,
    ) -> User | None:
        user = await UserRepository.show(session, user_id)
        if user is None:
            return None
        user.status = status.value
        await session.flush()
        return user

    @staticmethod
    async def destroy(session: AsyncSession, user_id: str) -> bool:
        stmt = (
            update(User)
            .where(User.id == user_id, User.deleted_at.is_(None))
            .values(deleted_at=datetime.now(UTC))
        )
        result = await session.execute(stmt)
        return result.rowcount > 0
