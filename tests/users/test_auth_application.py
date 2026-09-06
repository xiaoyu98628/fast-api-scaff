from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.config.database import DatabaseSettings
from app.contexts.user.application.auth_dto import LoginCommand
from app.contexts.user.application.auth_errors import AuthenticationRequiredError, InvalidCredentialsError, LoginUserNotFoundError
from app.contexts.user.application.dto import ChangeUserStatusCommand, CreateUserCommand, ResetUserPasswordCommand
from app.contexts.user.application.session_token import SessionCredential
from app.contexts.user.composition import UserContext, build_user_context
from app.contexts.user.domain.values import Password, PasswordHash, UserStatus
from app.contexts.user.infrastructure.persistence.models.session import UserSessionModel
from app.contexts.user.infrastructure.persistence.unit_of_work import SqlAlchemyUserUnitOfWork
from app.infrastructure.database.manager import DatabaseManager
from database.main.model_registry import load_main_database_metadata


class TrackingPasswordHasher:
    def __init__(self) -> None:
        self.checked: list[PasswordHash] = []
        self.after_verify: Callable[[], Awaitable[None]] | None = None

    async def hash(self, password: Password) -> PasswordHash:
        return PasswordHash(f"hash::{password.value}")

    async def verify(self, password: str, password_hash: PasswordHash) -> bool:
        self.checked.append(password_hash)
        if self.after_verify is not None:
            await self.after_verify()
        return password_hash.value == f"hash::{password}"


@dataclass
class AuthHarness:
    users: UserContext
    databases: DatabaseManager
    hasher: TrackingPasswordHasher
    now: datetime = datetime(2026, 9, 6, 12, 0)

    async def session_count(self) -> int:
        async with self.databases.session("main") as session:
            return (await session.scalar(select(func.count()).select_from(UserSessionModel))) or 0


@pytest_asyncio.fixture
async def harness() -> AsyncIterator[AuthHarness]:
    databases = DatabaseManager(DatabaseSettings(_env_file=None, connections={"main": {"driver": "sqlite", "database": ":memory:"}}))
    try:
        engine = await databases.get_engine("main")
        async with engine.begin() as connection:
            await connection.run_sync(load_main_database_metadata().create_all)
        hasher = TrackingPasswordHasher()
        users = build_user_context(databases, session_ttl_seconds=60)
        result = AuthHarness(users=users, databases=databases, hasher=hasher)
        result.users = replace(
            users,
            service=replace(users.service, password_hasher=hasher),
            auth=replace(users.auth, password_hasher=hasher, clock=lambda: result.now),
        )
        yield result
    finally:
        await databases.aclose()


@pytest.mark.asyncio
async def test_login_stores_only_digest_and_logout_affects_only_current_session(harness: AuthHarness) -> None:
    user = await harness.users.service.create(CreateUserCommand(username="alice", email="alice@example.com", password="password123"))
    first = await harness.users.auth.login(LoginCommand(username=" ALICE ", password="password123"))
    second = await harness.users.auth.login(LoginCommand(username="alice", password="password123"))
    first_credential = SessionCredential(first.access_token)
    second_credential = SessionCredential(second.access_token)

    assert first.access_token != second.access_token
    assert first.expires_in == 60
    assert (await harness.users.auth.current_user(first_credential)).id == user.id
    async with harness.databases.session("main") as session:
        stored = (await session.scalars(select(UserSessionModel))).all()
        assert len(stored) == 2
        assert {item.token_digest for item in stored} == {
            harness.users.auth.tokens.digest(first_credential),
            harness.users.auth.tokens.digest(second_credential),
        }
        assert all(item.token_digest not in {first.access_token, second.access_token} for item in stored)
        assert all(item.issued_at == harness.now and item.expires_at == harness.now + timedelta(seconds=60) for item in stored)

    await harness.users.auth.logout(first_credential)
    await harness.users.auth.logout(first_credential)
    with pytest.raises(AuthenticationRequiredError):
        await harness.users.auth.current_user(first_credential)
    assert (await harness.users.auth.current_user(second_credential)).id == user.id


@pytest.mark.parametrize(
    ("username", "password", "disabled"),
    [("alice", "wrong", False), ("alice", "password123", True)],
)
@pytest.mark.asyncio
async def test_login_failure_verifies_a_hash_and_creates_no_session(harness: AuthHarness, username: str, password: str, disabled: bool) -> None:
    user = await harness.users.service.create(CreateUserCommand(username="alice", email="alice@example.com", password="password123"))
    if disabled:
        await harness.users.service.change_status(ChangeUserStatusCommand(user_id=user.id, status=UserStatus.DISABLED))
    with pytest.raises(InvalidCredentialsError):
        await harness.users.auth.login(LoginCommand(username=username, password=password))
    assert len(harness.hasher.checked) == 1
    assert await harness.session_count() == 0


@pytest.mark.parametrize(("username", "error_type"), [("missing", LoginUserNotFoundError), ("!", InvalidCredentialsError)])
@pytest.mark.asyncio
async def test_login_rejects_missing_or_invalid_username_without_verifying_password(
    harness: AuthHarness, username: str, error_type: type[Exception]
) -> None:
    with pytest.raises(error_type):
        await harness.users.auth.login(LoginCommand(username=username, password="password123"))
    assert harness.hasher.checked == []
    assert await harness.session_count() == 0


@pytest.mark.asyncio
async def test_expiry_disable_reenable_password_reset_and_delete_contract(harness: AuthHarness) -> None:
    user = await harness.users.service.create(CreateUserCommand(username="alice", email="alice@example.com", password="password123"))
    token = await harness.users.auth.login(LoginCommand(username="alice", password="password123"))
    credential = SessionCredential(token.access_token)

    await harness.users.service.change_status(ChangeUserStatusCommand(user_id=user.id, status=UserStatus.DISABLED))
    with pytest.raises(AuthenticationRequiredError):
        await harness.users.auth.current_user(credential)
    await harness.users.service.change_status(ChangeUserStatusCommand(user_id=user.id, status=UserStatus.ACTIVE))
    assert (await harness.users.auth.current_user(credential)).id == user.id

    await harness.users.service.reset_password(ResetUserPasswordCommand(user_id=user.id, password="replacement-password"))
    assert (await harness.users.auth.current_user(credential)).id == user.id
    with pytest.raises(InvalidCredentialsError):
        await harness.users.auth.login(LoginCommand(username="alice", password="password123"))
    await harness.users.auth.login(LoginCommand(username="alice", password="replacement-password"))

    harness.now += timedelta(seconds=60)
    with pytest.raises(AuthenticationRequiredError):
        await harness.users.auth.current_user(credential)
    harness.now -= timedelta(microseconds=1)
    assert (await harness.users.auth.current_user(credential)).id == user.id
    await harness.users.service.delete(user.id)
    with pytest.raises(AuthenticationRequiredError):
        await harness.users.auth.current_user(credential)


@pytest.mark.parametrize("change", ["password", "status", "delete"])
@pytest.mark.asyncio
async def test_login_rechecks_account_after_password_verification(harness: AuthHarness, change: str) -> None:
    user = await harness.users.service.create(CreateUserCommand(username="alice", email="alice@example.com", password="password123"))

    async def modify_user() -> None:
        if change == "password":
            await harness.users.service.reset_password(ResetUserPasswordCommand(user_id=user.id, password="replacement-password"))
        elif change == "status":
            await harness.users.service.change_status(ChangeUserStatusCommand(user_id=user.id, status=UserStatus.DISABLED))
        else:
            await harness.users.service.delete(user.id)

    harness.hasher.after_verify = modify_user
    with pytest.raises(LoginUserNotFoundError if change == "delete" else InvalidCredentialsError):
        await harness.users.auth.login(LoginCommand(username="alice", password="password123"))
    assert await harness.session_count() == 0


@pytest.mark.asyncio
async def test_failed_session_commit_rolls_back(harness: AuthHarness, monkeypatch: pytest.MonkeyPatch) -> None:
    await harness.users.service.create(CreateUserCommand(username="alice", email="alice@example.com", password="password123"))

    async def fail_commit(uow: SqlAlchemyUserUnitOfWork) -> None:
        assert uow._session is not None
        await uow._session.flush()
        raise RuntimeError("commit failed")

    monkeypatch.setattr(SqlAlchemyUserUnitOfWork, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="commit failed"):
        await harness.users.auth.login(LoginCommand(username="alice", password="password123"))
    assert await harness.session_count() == 0
