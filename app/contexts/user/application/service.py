from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.contexts.user.application.dto import ChangeUserStatusCommand, CreateUserCommand, UpdateUserCommand, UserDTO, UserPageDTO
from app.contexts.user.application.errors import UserConflictError, UserNotFoundError
from app.contexts.user.application.password_hasher import PasswordHasher
from app.contexts.user.application.unit_of_work import UserUnitOfWorkFactory
from app.contexts.user.domain.repository import UserRepository
from app.contexts.user.domain.user import User
from app.contexts.user.domain.values import Password, UserId


@dataclass(frozen=True, slots=True)
class UserApplicationService:
    """编排用户管理用例，不依赖 HTTP 或 SQLAlchemy。"""

    unit_of_work_factory: UserUnitOfWorkFactory
    password_hasher: PasswordHasher
    clock: Callable[[], datetime] = datetime.now

    async def create(self, command: CreateUserCommand) -> UserDTO:
        password_hash = self.password_hasher.hash(Password(command.password))
        user = User.create(
            username=command.username,
            email=command.email,
            password_hash=password_hash,
            now=self.clock(),
        )

        async with self.unit_of_work_factory() as unit_of_work:
            await self._ensure_unique(unit_of_work.users, user)
            await unit_of_work.users.add(user)
            await unit_of_work.commit()

        return UserDTO.from_domain(user)

    async def get(self, user_id: UUID) -> UserDTO:
        async with self.unit_of_work_factory() as unit_of_work:
            user = await unit_of_work.users.find(UserId(user_id))

        if user is None:
            raise UserNotFoundError(user_id)

        return UserDTO.from_domain(user)

    async def list(self, *, offset: int, limit: int) -> UserPageDTO:
        async with self.unit_of_work_factory() as unit_of_work:
            users, total = await unit_of_work.users.find_page(offset=offset, limit=limit)

        return UserPageDTO(
            items=tuple(UserDTO.from_domain(user) for user in users),
            total=total,
            offset=offset,
            limit=limit,
        )

    async def update(self, command: UpdateUserCommand) -> UserDTO:
        user_id = UserId(command.user_id)

        async with self.unit_of_work_factory() as unit_of_work:
            user = await unit_of_work.users.find(user_id)
            if user is None:
                raise UserNotFoundError(command.user_id)

            user.update_profile(
                username=command.username,
                email=command.email,
                now=self.clock(),
            )
            await self._ensure_unique(unit_of_work.users, user)
            if not await unit_of_work.users.update(user):
                raise UserNotFoundError(command.user_id)

            await unit_of_work.commit()

        return UserDTO.from_domain(user)

    async def change_status(self, command: ChangeUserStatusCommand) -> UserDTO:
        user_id = UserId(command.user_id)

        async with self.unit_of_work_factory() as unit_of_work:
            user = await unit_of_work.users.find(user_id)
            if user is None:
                raise UserNotFoundError(command.user_id)

            user.change_status(status=command.status, now=self.clock())
            if not await unit_of_work.users.update(user):
                raise UserNotFoundError(command.user_id)

            await unit_of_work.commit()

        return UserDTO.from_domain(user)

    async def delete(self, user_id: UUID) -> None:
        domain_id = UserId(user_id)

        async with self.unit_of_work_factory() as unit_of_work:
            if not await unit_of_work.users.remove(domain_id):
                raise UserNotFoundError(user_id)

            await unit_of_work.commit()

    @staticmethod
    async def _ensure_unique(repository: UserRepository, user: User) -> None:
        if await repository.exists_by_username(user.username, excluding=user.id):
            raise UserConflictError("username")

        if await repository.exists_by_email(user.email, excluding=user.id):
            raise UserConflictError("email")
