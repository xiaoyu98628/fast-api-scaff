"""编排用户创建、查询、修改和删除用例。"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.contexts.user.application.dto import (
    ChangeUserStatusCommand,
    CreateUserCommand,
    ResetUserPasswordCommand,
    UpdateUserCommand,
    UserDTO,
    UserPageDTO,
)
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
        """创建用户，并在写入前检查用户名和邮箱唯一性。"""

        # 密码哈希可能是慢操作，先在事务外完成以缩短数据库占用时间。
        password_hash = await self.password_hasher.hash(Password(command.password))
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
        """按 ID 获取用户，不存在时抛出稳定的应用层异常。"""

        async with self.unit_of_work_factory() as unit_of_work:
            user = await unit_of_work.users.find(UserId(user_id))

        if user is None:
            raise UserNotFoundError(user_id)

        return UserDTO.from_domain(user)

    async def list(self, *, offset: int, limit: int) -> UserPageDTO:
        """返回指定偏移量和数量限制的一页用户。"""

        async with self.unit_of_work_factory() as unit_of_work:
            users, total = await unit_of_work.users.find_page(offset=offset, limit=limit)

        return UserPageDTO(
            items=tuple(UserDTO.from_domain(user) for user in users),
            total=total,
            offset=offset,
            limit=limit,
        )

    async def update(self, command: UpdateUserCommand) -> UserDTO:
        """修改用户名和邮箱，并重新检查唯一性。"""

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
        """修改账户启用状态。"""

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

    async def reset_password(self, command: ResetUserPasswordCommand) -> None:
        """在事务外生成新哈希，再替换目标用户密码。"""

        user_id = UserId(command.user_id)
        password_hash = await self.password_hasher.hash(Password(command.password))

        async with self.unit_of_work_factory() as unit_of_work:
            user = await unit_of_work.users.find(user_id)
            if user is None:
                raise UserNotFoundError(command.user_id)

            user.reset_password(password_hash=password_hash, now=self.clock())
            if not await unit_of_work.users.update(user):
                raise UserNotFoundError(command.user_id)

            await unit_of_work.commit()

    async def delete(self, user_id: UUID) -> None:
        """删除目标用户，不存在时抛出应用层异常。"""

        domain_id = UserId(user_id)

        async with self.unit_of_work_factory() as unit_of_work:
            if not await unit_of_work.users.remove(domain_id):
                raise UserNotFoundError(user_id)

            await unit_of_work.commit()

    @staticmethod
    async def _ensure_unique(repository: UserRepository, user: User) -> None:
        """排除当前用户后检查用户名和邮箱占用情况。"""

        if await repository.exists_by_username(user.username, excluding=user.id):
            raise UserConflictError("username")

        if await repository.exists_by_email(user.email, excluding=user.id):
            raise UserConflictError("email")
