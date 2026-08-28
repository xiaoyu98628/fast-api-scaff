from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.user_management.domain.user import User
from app.contexts.user_management.domain.values import EmailAddress, UserId, Username
from app.contexts.user_management.infrastructure.persistence.mapper import update_user_record, user_to_domain, user_to_record
from app.contexts.user_management.infrastructure.persistence.model import UserRecord


class SqlAlchemyUserRepository:
    """使用 SQLAlchemy 实现用户 Repository 契约。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find(self, user_id: UserId) -> User | None:
        record = await self._session.get(UserRecord, user_id.value)
        return user_to_domain(record) if record is not None else None

    async def exists_by_username(self, username: Username, *, excluding: UserId | None = None) -> bool:
        statement = select(UserRecord.id).where(UserRecord.username == username.value)
        if excluding is not None:
            statement = statement.where(UserRecord.id != excluding.value)

        return (await self._session.scalar(statement.limit(1))) is not None

    async def exists_by_email(self, email: EmailAddress, *, excluding: UserId | None = None) -> bool:
        statement = select(UserRecord.id).where(UserRecord.email == email.value)
        if excluding is not None:
            statement = statement.where(UserRecord.id != excluding.value)

        return (await self._session.scalar(statement.limit(1))) is not None

    async def find_page(self, *, offset: int, limit: int) -> tuple[list[User], int]:
        total = await self._session.scalar(select(func.count()).select_from(UserRecord))
        statement = select(UserRecord).order_by(UserRecord.created_at.desc(), UserRecord.id.desc()).offset(offset).limit(limit)
        records = (await self._session.scalars(statement)).all()

        return [user_to_domain(record) for record in records], total or 0

    async def add(self, user: User) -> None:
        self._session.add(user_to_record(user))

    async def update(self, user: User) -> None:
        record = await self._session.get(UserRecord, user.id.value)
        if record is not None:
            update_user_record(record, user)

    async def remove(self, user_id: UserId) -> None:
        record = await self._session.get(UserRecord, user_id.value)
        if record is not None:
            await self._session.delete(record)
