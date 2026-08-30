from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.user.domain.user import User
from app.contexts.user.domain.values import EmailAddress, UserId, Username
from app.contexts.user.infrastructure.persistence.mapper import update_user_model, user_to_domain, user_to_model
from app.contexts.user.infrastructure.persistence.models.user import UserModel


class SqlAlchemyUserRepository:
    """使用 SQLAlchemy 实现用户 Repository 契约。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find(self, user_id: UserId) -> User | None:
        model = await self._session.get(UserModel, user_id.value)
        return user_to_domain(model) if model is not None else None

    async def exists_by_username(self, username: Username, *, excluding: UserId | None = None) -> bool:
        statement = select(UserModel.id).where(UserModel.username == username.value)
        if excluding is not None:
            statement = statement.where(UserModel.id != excluding.value)

        return (await self._session.scalar(statement.limit(1))) is not None

    async def exists_by_email(self, email: EmailAddress, *, excluding: UserId | None = None) -> bool:
        statement = select(UserModel.id).where(UserModel.email == email.value)
        if excluding is not None:
            statement = statement.where(UserModel.id != excluding.value)

        return (await self._session.scalar(statement.limit(1))) is not None

    async def find_page(self, *, offset: int, limit: int) -> tuple[list[User], int]:
        total = await self._session.scalar(select(func.count()).select_from(UserModel))
        statement = select(UserModel).order_by(UserModel.created_at.desc(), UserModel.id.desc()).offset(offset).limit(limit)
        models = (await self._session.scalars(statement)).all()

        return [user_to_domain(model) for model in models], total or 0

    async def add(self, user: User) -> None:
        self._session.add(user_to_model(user))

    async def update(self, user: User) -> None:
        model = await self._session.get(UserModel, user.id.value)
        if model is not None:
            update_user_model(model, user)

    async def remove(self, user_id: UserId) -> None:
        model = await self._session.get(UserModel, user_id.value)
        if model is not None:
            await self._session.delete(model)
