import logging

from app.application.support.pagination import PageResult
from app.application.support.ulid import generate_ulid
from app.application.user.security import hash_password
from app.domain.user.entity import User
from app.domain.user.enums import UserStatus
from app.domain.user.exceptions import InvalidUserUpdateError, UsernameAlreadyExistsError, UserNotFoundError
from app.infrastructure.database.session import SessionProvider
from app.infrastructure.persistence.repositories.user import UserRepositoryImpl

logger = logging.getLogger(__name__)


class UserService:
    """用户应用服务。"""

    def __init__(self, session_provider: SessionProvider | None = None) -> None:
        self._session_provider = session_provider or SessionProvider()

    async def create_user(
        self,
        *,
        username: str,
        password: str,
        nickname: str,
        status: UserStatus = UserStatus.ACTIVATION,
    ) -> User:
        async with self._session_provider.session() as session:
            repo = UserRepositoryImpl(session)
            existing = await repo.get_by_username(username)
            if existing is not None:
                raise UsernameAlreadyExistsError(username)

            user = await repo.create(
                user_id=generate_ulid(),
                username=username,
                password_hash=hash_password(password),
                nickname=nickname,
                status=status,
            )
            await session.commit()
            logger.info("user created", extra={"user_id": user.id, "username": user.username})
            return user

    async def get_user(self, user_id: str) -> User:
        async with self._session_provider.session() as session:
            repo = UserRepositoryImpl(session)
            user = await repo.get_by_id(user_id)
            if user is None:
                raise UserNotFoundError(user_id)
            return user

    async def update_user(
        self,
        user_id: str,
        *,
        nickname: str | None = None,
        password: str | None = None,
        status: UserStatus | None = None,
    ) -> User:
        if nickname is None and password is None and status is None:
            raise InvalidUserUpdateError("至少提供一个可更新字段")

        async with self._session_provider.session() as session:
            repo = UserRepositoryImpl(session)
            user = await repo.update(
                user_id,
                nickname=nickname,
                password_hash=hash_password(password) if password is not None else None,
                status=status,
            )
            if user is None:
                raise UserNotFoundError(user_id)

            await session.commit()
            logger.info("user updated", extra={"user_id": user.id})
            return user

    async def delete_user(self, user_id: str) -> None:
        async with self._session_provider.session() as session:
            repo = UserRepositoryImpl(session)
            deleted = await repo.soft_delete(user_id)
            if not deleted:
                raise UserNotFoundError(user_id)
            await session.commit()
            logger.info("user deleted", extra={"user_id": user_id})

    async def list_users(
        self,
        *,
        page: int,
        page_size: int,
        keyword: str | None = None,
    ) -> PageResult[User]:
        async with self._session_provider.session() as session:
            repo = UserRepositoryImpl(session)
            items, total = await repo.page(
                page=page,
                page_size=page_size,
                keyword=keyword,
            )
            logger.debug(
                "users listed",
                extra={"page": page, "page_size": page_size, "total": total, "keyword": keyword},
            )
            return PageResult(
                items=items,
                total=total,
                page=page,
                page_size=page_size,
            )
