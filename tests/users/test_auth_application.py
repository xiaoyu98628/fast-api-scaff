"""验证认证应用服务的登录、会话和并发边界。"""

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.config.app import AppSettings
from app.config.auth import AuthSettings
from app.config.cache import CacheSettings
from app.config.cors import CorsSettings
from app.config.database import DatabaseSettings
from app.config.settings import Settings
from app.contexts.user.application.auth_dto import LoginCommand
from app.contexts.user.application.auth_errors import (
    AuthenticationRequiredError,
    InvalidCredentialsError,
    LoginTemporarilyLockedError,
)
from app.contexts.user.application.dto import ChangeUserStatusCommand, CreateUserCommand, ResetUserPasswordCommand
from app.contexts.user.application.login_attempts import LoginFailureStatus
from app.contexts.user.application.session_token import SessionCredential
from app.contexts.user.composition import UserContext, build_user_context
from app.contexts.user.domain.values import Password, PasswordHash, UserStatus
from app.contexts.user.infrastructure.persistence.models.session import UserSessionModel
from app.contexts.user.infrastructure.persistence.unit_of_work import SqlAlchemyUserUnitOfWork
from app.infrastructure.cache.manager import CacheManager
from app.infrastructure.database.manager import DatabaseManager
from database.main.model_registry import load_main_database_metadata


class TrackingPasswordHasher:
    def __init__(self) -> None:
        self.checked: list[PasswordHash | None] = []
        self.after_verify: Callable[[], Awaitable[None]] | None = None

    async def hash(self, password: Password) -> PasswordHash:
        return PasswordHash(f"hash::{password.value}")

    async def verify_or_dummy(self, password: str, password_hash: PasswordHash | None) -> bool:
        self.checked.append(password_hash)
        if self.after_verify is not None:
            await self.after_verify()
        return password_hash is not None and password_hash.value == f"hash::{password}"


class TrackingLoginAttemptLimiter:
    def __init__(
        self,
        *,
        retry_after: int | None = None,
        remaining_attempts: int = 4,
        failure_retry_after: int | None = None,
        clear_error: Exception | None = None,
    ) -> None:
        self.retry_after_seconds = retry_after
        self.remaining_attempts = remaining_attempts
        self.failure_retry_after = failure_retry_after
        self.clear_error = clear_error
        self.checked: list[str] = []
        self.failures: list[str] = []
        self.cleared: list[str] = []

    async def retry_after(self, identity: str) -> int | None:
        self.checked.append(identity)
        return self.retry_after_seconds

    async def record_failure(self, identity: str) -> LoginFailureStatus:
        self.failures.append(identity)
        if self.failure_retry_after is not None:
            return LoginFailureStatus(remaining_attempts=0, retry_after_seconds=self.failure_retry_after)
        return LoginFailureStatus(remaining_attempts=self.remaining_attempts)

    async def clear(self, identity: str) -> None:
        self.cleared.append(identity)
        if self.clear_error is not None:
            raise self.clear_error


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
    settings = Settings(
        app=AppSettings(_env_file=None),
        auth=AuthSettings(session_ttl_seconds=60, login_limit_cache=None, _env_file=None),
        database=DatabaseSettings(_env_file=None, connections={"main": {"driver": "sqlite", "database": ":memory:"}}),
        cache=CacheSettings(_env_file=None),
        cors=CorsSettings(_env_file=None),
    )
    databases = DatabaseManager(settings.database)
    caches = CacheManager(settings.cache)
    try:
        engine = await databases.get_engine("main")
        async with engine.begin() as connection:
            await connection.run_sync(load_main_database_metadata().create_all)
        hasher = TrackingPasswordHasher()
        users = build_user_context(settings, databases, caches)
        result = AuthHarness(users=users, databases=databases, hasher=hasher)
        result.users = replace(
            users,
            service=replace(users.service, password_hasher=hasher),
            auth=replace(users.auth, password_hasher=hasher, clock=lambda: result.now),
        )
        yield result
    finally:
        await caches.aclose()
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
    assert first.user_id == user.id
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


@pytest.mark.asyncio
async def test_successful_login_removes_only_expired_sessions(harness: AuthHarness) -> None:
    await harness.users.service.create(CreateUserCommand(username="alice", email="alice@example.com", password="password123"))
    expired = await harness.users.auth.login(LoginCommand(username="alice", password="password123"))
    harness.now += timedelta(seconds=30)
    active = await harness.users.auth.login(LoginCommand(username="alice", password="password123"))
    harness.now += timedelta(seconds=30)

    current = await harness.users.auth.login(LoginCommand(username="alice", password="password123"))

    expired_digest = harness.users.auth.tokens.digest(SessionCredential(expired.access_token))
    active_digest = harness.users.auth.tokens.digest(SessionCredential(active.access_token))
    current_digest = harness.users.auth.tokens.digest(SessionCredential(current.access_token))
    async with harness.databases.session("main") as session:
        stored_digests = set(await session.scalars(select(UserSessionModel.token_digest)))

    assert stored_digests == {active_digest, current_digest}
    assert expired_digest not in stored_digests


@pytest.mark.asyncio
async def test_cleanup_expired_sessions_removes_only_expired_sessions(harness: AuthHarness) -> None:
    await harness.users.service.create(CreateUserCommand(username="alice", email="alice@example.com", password="password123"))
    expired = await harness.users.auth.login(LoginCommand(username="alice", password="password123"))
    harness.now += timedelta(seconds=30)
    active = await harness.users.auth.login(LoginCommand(username="alice", password="password123"))
    harness.now += timedelta(seconds=30)

    removed_count = await harness.users.auth.cleanup_expired_sessions()

    expired_digest = harness.users.auth.tokens.digest(SessionCredential(expired.access_token))
    active_digest = harness.users.auth.tokens.digest(SessionCredential(active.access_token))
    async with harness.databases.session("main") as session:
        stored_digests = set(await session.scalars(select(UserSessionModel.token_digest)))

    assert removed_count == 1
    assert stored_digests == {active_digest}
    assert expired_digest not in stored_digests


@pytest.mark.parametrize(
    ("username", "password", "disabled"),
    [("alice", "wrong", False), ("alice", "password123", True)],
)
@pytest.mark.asyncio
async def test_login_failure_verifies_a_hash_and_creates_no_session(harness: AuthHarness, username: str, password: str, disabled: bool) -> None:
    user = await harness.users.service.create(CreateUserCommand(username="alice", email="alice@example.com", password="password123"))
    if disabled:
        await harness.users.service.change_status(ChangeUserStatusCommand(user_id=user.id, status=UserStatus.DISABLED))
    limiter = TrackingLoginAttemptLimiter()
    harness.users = replace(harness.users, auth=replace(harness.users.auth, login_attempts=limiter))
    with pytest.raises(InvalidCredentialsError) as captured:
        await harness.users.auth.login(LoginCommand(username=username, password=password))
    assert len(harness.hasher.checked) == 1
    assert captured.value.remaining_attempts == 4
    assert limiter.failures == [username.strip().lower()]
    assert await harness.session_count() == 0


@pytest.mark.parametrize("username", ["missing", "!"])
@pytest.mark.asyncio
async def test_login_rejects_missing_or_invalid_username_with_dummy_verification(harness: AuthHarness, username: str) -> None:
    limiter = TrackingLoginAttemptLimiter()
    harness.users = replace(harness.users, auth=replace(harness.users.auth, login_attempts=limiter))
    with pytest.raises(InvalidCredentialsError) as captured:
        await harness.users.auth.login(LoginCommand(username=username, password="password123"))
    assert harness.hasher.checked == [None]
    assert captured.value.remaining_attempts == 4
    assert limiter.failures == [username.strip().lower()]
    assert await harness.session_count() == 0


@pytest.mark.asyncio
async def test_locked_login_skips_password_hash_and_reports_retry_after(harness: AuthHarness) -> None:
    limiter = TrackingLoginAttemptLimiter(retry_after=120)
    harness.users = replace(harness.users, auth=replace(harness.users.auth, login_attempts=limiter))

    with pytest.raises(LoginTemporarilyLockedError) as captured:
        await harness.users.auth.login(LoginCommand(username=" ALICE ", password="password123"))

    assert captured.value.retry_after_seconds == 120
    assert limiter.checked == ["alice"]
    assert limiter.failures == []
    assert harness.hasher.checked == []
    assert await harness.session_count() == 0


@pytest.mark.asyncio
async def test_failure_that_reaches_threshold_returns_lock_error(harness: AuthHarness) -> None:
    await harness.users.service.create(CreateUserCommand(username="alice", email="alice@example.com", password="password123"))
    limiter = TrackingLoginAttemptLimiter(failure_retry_after=900)
    harness.users = replace(harness.users, auth=replace(harness.users.auth, login_attempts=limiter))

    with pytest.raises(LoginTemporarilyLockedError) as captured:
        await harness.users.auth.login(LoginCommand(username="alice", password="wrong"))

    assert captured.value.retry_after_seconds == 900
    assert limiter.failures == ["alice"]
    assert await harness.session_count() == 0


@pytest.mark.asyncio
async def test_successful_login_clears_previous_failures(harness: AuthHarness) -> None:
    await harness.users.service.create(CreateUserCommand(username="alice", email="alice@example.com", password="password123"))
    limiter = TrackingLoginAttemptLimiter()
    harness.users = replace(harness.users, auth=replace(harness.users.auth, login_attempts=limiter))

    await harness.users.auth.login(LoginCommand(username=" ALICE ", password="password123"))

    assert limiter.checked == ["alice"]
    assert limiter.failures == []
    assert limiter.cleared == ["alice"]


@pytest.mark.asyncio
async def test_failed_attempt_cleanup_rolls_back_new_session(harness: AuthHarness) -> None:
    await harness.users.service.create(CreateUserCommand(username="alice", email="alice@example.com", password="password123"))
    limiter = TrackingLoginAttemptLimiter(clear_error=RuntimeError("cache unavailable"))
    harness.users = replace(harness.users, auth=replace(harness.users.auth, login_attempts=limiter))

    with pytest.raises(RuntimeError, match="cache unavailable"):
        await harness.users.auth.login(LoginCommand(username="alice", password="password123"))

    assert limiter.cleared == ["alice"]
    assert await harness.session_count() == 0


@pytest.mark.asyncio
async def test_expiry_disable_reenable_password_reset_and_delete_contract(harness: AuthHarness) -> None:
    user = await harness.users.service.create(CreateUserCommand(username="alice", email="alice@example.com", password="password123"))
    token = await harness.users.auth.login(LoginCommand(username="alice", password="password123"))
    disabled_credential = SessionCredential(token.access_token)

    await harness.users.service.change_status(ChangeUserStatusCommand(user_id=user.id, status=UserStatus.DISABLED))
    with pytest.raises(AuthenticationRequiredError):
        await harness.users.auth.current_user(disabled_credential)
    assert await harness.session_count() == 0

    await harness.users.service.change_status(ChangeUserStatusCommand(user_id=user.id, status=UserStatus.ACTIVE))
    with pytest.raises(AuthenticationRequiredError):
        await harness.users.auth.current_user(disabled_credential)

    active_token = await harness.users.auth.login(LoginCommand(username="alice", password="password123"))
    active_credential = SessionCredential(active_token.access_token)
    await harness.users.service.reset_password(ResetUserPasswordCommand(user_id=user.id, password="replacement-password"))
    with pytest.raises(AuthenticationRequiredError):
        await harness.users.auth.current_user(active_credential)
    assert await harness.session_count() == 0

    with pytest.raises(InvalidCredentialsError):
        await harness.users.auth.login(LoginCommand(username="alice", password="password123"))
    replacement = await harness.users.auth.login(LoginCommand(username="alice", password="replacement-password"))
    replacement_credential = SessionCredential(replacement.access_token)

    harness.now += timedelta(seconds=60)
    with pytest.raises(AuthenticationRequiredError):
        await harness.users.auth.current_user(replacement_credential)
    harness.now -= timedelta(microseconds=1)
    assert (await harness.users.auth.current_user(replacement_credential)).id == user.id
    await harness.users.service.delete(user.id)
    with pytest.raises(AuthenticationRequiredError):
        await harness.users.auth.current_user(replacement_credential)


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
    with pytest.raises(InvalidCredentialsError):
        await harness.users.auth.login(LoginCommand(username="alice", password="password123"))
    assert await harness.session_count() == 0


@pytest.mark.asyncio
async def test_failed_session_commit_rolls_back(harness: AuthHarness, monkeypatch: pytest.MonkeyPatch) -> None:
    await harness.users.service.create(CreateUserCommand(username="alice", email="alice@example.com", password="password123"))
    limiter = TrackingLoginAttemptLimiter()
    harness.users = replace(harness.users, auth=replace(harness.users.auth, login_attempts=limiter))

    async def fail_commit(uow: SqlAlchemyUserUnitOfWork) -> None:
        assert uow._session is not None
        await uow._session.flush()
        raise RuntimeError("commit failed")

    monkeypatch.setattr(SqlAlchemyUserUnitOfWork, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="commit failed"):
        await harness.users.auth.login(LoginCommand(username="alice", password="password123"))
    assert limiter.cleared == ["alice"]
    assert await harness.session_count() == 0


@pytest.mark.asyncio
async def test_inflight_success_does_not_clear_lock_created_during_password_verification(harness: AuthHarness) -> None:
    from tests.users.test_login_attempt_limiter import FakeRedisCacheClient, build_limiter

    await harness.users.service.create(CreateUserCommand(username="alice", email="alice@example.com", password="password123"))
    client = FakeRedisCacheClient()
    limiter = build_limiter(client)
    harness.users = replace(harness.users, auth=replace(harness.users.auth, login_attempts=limiter))
    for _ in range(4):
        await limiter.record_failure("alice")

    async def establish_lock() -> None:
        # 精确插入在入口检查之后、成功清理之前，模拟另一请求达到失败阈值。
        await limiter.record_failure("alice")

    harness.hasher.after_verify = establish_lock
    result = await harness.users.auth.login(LoginCommand(username="alice", password="password123"))
    assert result.access_token
    assert await harness.session_count() == 1
    assert await limiter.retry_after("alice") == 900
    with pytest.raises(LoginTemporarilyLockedError):
        await harness.users.auth.login(LoginCommand(username="alice", password="password123"))
    assert await harness.session_count() == 1
