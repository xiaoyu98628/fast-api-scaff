from datetime import datetime
from types import TracebackType
from uuid import UUID

import pytest

from app.contexts.user.application.dto import ChangeUserStatusCommand, CreateUserCommand, ResetUserPasswordCommand, UpdateUserCommand
from app.contexts.user.application.errors import UserConflictError, UserNotFoundError
from app.contexts.user.application.service import UserApplicationService
from app.contexts.user.domain.repository import UserRepository
from app.contexts.user.domain.user import User
from app.contexts.user.domain.values import EmailAddress, Password, PasswordHash, UserId, Username, UserStatus


class FakePasswordHasher:
    def __init__(self) -> None:
        self.passwords: list[str] = []

    async def hash(self, password: Password) -> PasswordHash:
        self.passwords.append(password.value)
        return PasswordHash(f"hashed::{password.value}")


class FakeUserRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, User] = {}
        self.remove_before_update = False

    async def find(self, user_id: UserId) -> User | None:
        return self.items.get(user_id.value)

    async def exists_by_username(self, username: Username, *, excluding: UserId | None = None) -> bool:
        return any(user.username == username and (excluding is None or user.id != excluding) for user in self.items.values())

    async def exists_by_email(self, email: EmailAddress, *, excluding: UserId | None = None) -> bool:
        return any(user.email == email and (excluding is None or user.id != excluding) for user in self.items.values())

    async def find_page(self, *, offset: int, limit: int) -> tuple[list[User], int]:
        users = list(self.items.values())
        return users[offset : offset + limit], len(users)

    async def add(self, user: User) -> None:
        self.items[user.id.value] = user

    async def update(self, user: User) -> bool:
        if self.remove_before_update:
            self.items.pop(user.id.value, None)

        if user.id.value not in self.items:
            return False

        self.items[user.id.value] = user
        return True

    async def remove(self, user_id: UserId) -> bool:
        return self.items.pop(user_id.value, None) is not None


class FakeUserUnitOfWork:
    def __init__(self, repository: UserRepository) -> None:
        self._users = repository
        self.commit_count = 0

    @property
    def users(self) -> UserRepository:
        return self._users

    async def __aenter__(self) -> FakeUserUnitOfWork:
        return self

    async def __aexit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exception_type, exception, traceback
        return None

    async def commit(self) -> None:
        self.commit_count += 1


def build_service(repository: FakeUserRepository, password_hasher: FakePasswordHasher | None = None) -> UserApplicationService:
    return UserApplicationService(
        unit_of_work_factory=lambda: FakeUserUnitOfWork(repository),
        password_hasher=password_hasher or FakePasswordHasher(),
        clock=lambda: datetime(2026, 8, 28, 18, 0),
    )


@pytest.mark.asyncio
async def test_user_service_hashes_password_before_persisting_user() -> None:
    repository = FakeUserRepository()
    password_hasher = FakePasswordHasher()
    service = build_service(repository, password_hasher)

    created = await service.create(CreateUserCommand(username="alice", email="alice@example.com", password="password123"))

    stored = repository.items[created.id]
    assert password_hasher.passwords == ["password123"]
    assert stored.password_hash == PasswordHash("hashed::password123")
    assert not hasattr(created, "password")
    assert not hasattr(created, "password_hash")


@pytest.mark.asyncio
async def test_user_service_rejects_invalid_password_before_hashing() -> None:
    repository = FakeUserRepository()
    password_hasher = FakePasswordHasher()
    service = build_service(repository, password_hasher)

    with pytest.raises(ValueError, match="密码长度"):
        await service.create(CreateUserCommand(username="alice", email="alice@example.com", password="short"))

    assert password_hasher.passwords == []
    assert repository.items == {}


@pytest.mark.asyncio
async def test_user_service_resets_password_with_a_new_hash() -> None:
    repository = FakeUserRepository()
    password_hasher = FakePasswordHasher()
    service = build_service(repository, password_hasher)
    created = await service.create(CreateUserCommand(username="alice", email="alice@example.com", password="password123"))
    original_password_hash = repository.items[created.id].password_hash

    await service.reset_password(ResetUserPasswordCommand(user_id=created.id, password="replacement-password"))

    reset_password_hash = repository.items[created.id].password_hash
    assert password_hasher.passwords == ["password123", "replacement-password"]
    assert reset_password_hash == PasswordHash("hashed::replacement-password")
    assert reset_password_hash != original_password_hash


@pytest.mark.asyncio
async def test_user_service_completes_crud_flow() -> None:
    repository = FakeUserRepository()
    service = build_service(repository)

    created = await service.create(CreateUserCommand(username="alice", email="alice@example.com", password="password123"))
    fetched = await service.get(created.id)
    page = await service.list(offset=0, limit=20)
    updated = await service.update(
        UpdateUserCommand(
            user_id=created.id,
            username="alice_new",
            email="new@example.com",
        )
    )
    status_changed = await service.change_status(
        ChangeUserStatusCommand(
            user_id=created.id,
            status=UserStatus.DISABLED,
        )
    )
    await service.delete(created.id)

    assert fetched == created
    assert page.total == 1
    assert page.items == (created,)
    assert updated.username == "alice_new"
    assert updated.status is UserStatus.ACTIVE
    assert status_changed.status is UserStatus.DISABLED
    assert repository.items == {}

    with pytest.raises(UserNotFoundError):
        await service.get(created.id)


@pytest.mark.asyncio
async def test_user_service_rejects_duplicate_username_and_email() -> None:
    repository = FakeUserRepository()
    service = build_service(repository)
    await service.create(CreateUserCommand(username="alice", email="alice@example.com", password="password123"))

    with pytest.raises(UserConflictError) as username_error:
        await service.create(CreateUserCommand(username="alice", email="other@example.com", password="password123"))

    with pytest.raises(UserConflictError) as email_error:
        await service.create(CreateUserCommand(username="other", email="alice@example.com", password="password123"))

    assert username_error.value.field == "username"
    assert email_error.value.field == "email"


@pytest.mark.asyncio
async def test_user_service_reports_not_found_when_update_target_disappears() -> None:
    repository = FakeUserRepository()
    service = build_service(repository)
    created = await service.create(CreateUserCommand(username="alice", email="alice@example.com", password="password123"))
    repository.remove_before_update = True

    with pytest.raises(UserNotFoundError):
        await service.update(
            UpdateUserCommand(
                user_id=created.id,
                username="alice_new",
                email="new@example.com",
            )
        )


@pytest.mark.asyncio
async def test_user_service_reports_not_found_when_status_target_disappears() -> None:
    repository = FakeUserRepository()
    service = build_service(repository)
    created = await service.create(CreateUserCommand(username="alice", email="alice@example.com", password="password123"))
    repository.remove_before_update = True

    with pytest.raises(UserNotFoundError):
        await service.change_status(
            ChangeUserStatusCommand(
                user_id=created.id,
                status=UserStatus.DISABLED,
            )
        )


@pytest.mark.asyncio
async def test_user_service_reports_not_found_when_password_target_disappears() -> None:
    repository = FakeUserRepository()
    service = build_service(repository)
    created = await service.create(CreateUserCommand(username="alice", email="alice@example.com", password="password123"))
    repository.remove_before_update = True

    with pytest.raises(UserNotFoundError):
        await service.reset_password(ResetUserPasswordCommand(user_id=created.id, password="replacement-password"))


@pytest.mark.asyncio
async def test_user_service_reports_not_found_when_delete_matches_nothing() -> None:
    repository = FakeUserRepository()
    service = build_service(repository)

    with pytest.raises(UserNotFoundError):
        await service.delete(UUID("00000000-0000-0000-0000-000000000002"))
