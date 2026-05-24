from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.user.entity import User as UserEntity
from app.domain.user.enums import UserStatus
from app.domain.user.repository import UserRepository
from app.infrastructure.persistence.models.user import User as UserModel
from app.infrastructure.persistence.pagination import paginate


class UserRepositoryImpl(UserRepository):
    """用户仓储 SQLAlchemy 实现。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: str) -> UserEntity | None:
        model = await self._session.get(UserModel, user_id)
        if model is None or model.deleted_at is not None:
            return None
        return self._to_entity(model)

    async def get_by_username(self, username: str) -> UserEntity | None:
        stmt = select(UserModel).where(
            UserModel.username == username,
            UserModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_entity(model)

    async def create(
        self,
        user_id: str,
        username: str,
        password_hash: str,
        nickname: str,
        status: UserStatus,
    ) -> UserEntity:
        model = UserModel(
            id=user_id,
            username=username,
            password=password_hash,
            nickname=nickname,
            status=status.value,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_entity(model)

    async def update(
        self,
        user_id: str,
        *,
        nickname: str | None = None,
        password_hash: str | None = None,
        status: UserStatus | None = None,
    ) -> UserEntity | None:
        model = await self._session.get(UserModel, user_id)
        if model is None or model.deleted_at is not None:
            return None

        if nickname is not None:
            model.nickname = nickname
        if password_hash is not None:
            model.password = password_hash
        if status is not None:
            model.status = status.value

        await self._session.flush()
        await self._session.refresh(model)
        return self._to_entity(model)

    async def soft_delete(self, user_id: str) -> bool:
        model = await self._session.get(UserModel, user_id)
        if model is None or model.deleted_at is not None:
            return False

        model.deleted_at = datetime.now(UTC).replace(tzinfo=None)
        await self._session.flush()
        return True

    async def page(
        self,
        *,
        page: int,
        page_size: int,
        keyword: str | None = None,
    ) -> tuple[list[UserEntity], int]:
        conditions = [UserModel.deleted_at.is_(None)]
        if keyword:
            pattern = f"%{keyword}%"
            conditions.append(
                or_(
                    UserModel.username.like(pattern),
                    UserModel.nickname.like(pattern),
                )
            )

        count_stmt = select(func.count()).select_from(UserModel).where(*conditions)
        data_stmt = select(UserModel).where(*conditions).order_by(UserModel.created_at.desc())
        models, total = await paginate(
            self._session,
            count_stmt=count_stmt,
            data_stmt=data_stmt,
            page=page,
            page_size=page_size,
        )
        return [self._to_entity(model) for model in models], total

    @staticmethod
    def _to_entity(model: UserModel) -> UserEntity:
        return UserEntity(
            id=model.id,
            username=model.username,
            nickname=model.nickname,
            status=UserStatus(model.status),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
