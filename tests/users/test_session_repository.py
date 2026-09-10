"""验证用户会话仓储和事务持久化。"""

from dataclasses import fields
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import uuid7

import pytest
from pydantic import ValidationError
from sqlalchemy import DateTime, text

from app.config.auth import AuthSettings
from app.config.database import DatabaseSettings
from app.contexts.user.application.auth_dto import LoginCommand, TokenDTO
from app.contexts.user.application.auth_errors import AuthenticationRequiredError, InvalidCredentialsError
from app.contexts.user.application.session_token import SessionCredential
from app.contexts.user.domain.session import UserSession
from app.contexts.user.domain.user import User
from app.contexts.user.domain.values import PasswordHash, UserId
from app.contexts.user.infrastructure.persistence.models.session import UserSessionModel
from app.contexts.user.infrastructure.persistence.models.user import UserModel
from app.contexts.user.infrastructure.persistence.unit_of_work import SqlAlchemyUserUnitOfWork
from app.contexts.user.infrastructure.security.session_token import SecureSessionTokenCodec
from app.infrastructure.database.manager import DatabaseManager
from database.main.model_registry import load_main_database_metadata


def test_token_and_session_hide_secrets_and_expire_at_boundary() -> None:
    codec = SecureSessionTokenCodec()
    credential = codec.issue()
    digest = codec.digest(credential)
    issued_at = datetime(2026, 9, 6, 12, 0)
    expires_at = issued_at + timedelta(seconds=100)
    session = UserSession(token_digest=digest, user_id=UserId(uuid7()), issued_at=issued_at, expires_at=expires_at)
    assert credential.token not in repr(credential)
    assert digest not in repr(session)
    assert session.is_valid(now=issued_at)
    assert session.is_valid(now=expires_at - timedelta(microseconds=1))
    assert not session.is_valid(now=expires_at)
    assert not session.is_valid(now=issued_at - timedelta(microseconds=1))
    assert "secret-password" not in repr(LoginCommand(username="alice", password="secret-password"))
    assert credential.token not in repr(TokenDTO(access_token=credential.token, expires_in=100, user_id=uuid7()))
    assert set(UserModel.__table__.columns.keys()) == {"id", "username", "email", "password", "status", "created_at", "updated_at"}
    assert {field.name for field in fields(UserSession)} == {"token_digest", "user_id", "issued_at", "expires_at"}
    assert "user_sessions" in load_main_database_metadata().tables
    for name in ("issued_at", "expires_at"):
        column = UserSessionModel.__table__.c[name]
        assert isinstance(column.type, DateTime)
        assert column.type.timezone is False


@pytest.mark.parametrize("token", ["", "a" * 42, "a" * 44, " " * 43, "中" * 43])
def test_invalid_token_is_rejected(token: str) -> None:
    with pytest.raises(AuthenticationRequiredError):
        SessionCredential(token)


@pytest.mark.parametrize(
    ("issued", "expires"),
    [
        (datetime(2026, 9, 6, 12), datetime(2026, 9, 6, 12)),
        (datetime(2026, 9, 6, 12), datetime(2026, 9, 6, 11)),
        (datetime(2026, 9, 6, 12, tzinfo=UTC), datetime(2026, 9, 6, 13)),
        (datetime(2026, 9, 6, 12), datetime(2026, 9, 6, 13, tzinfo=UTC)),
        (100, datetime(2026, 9, 6, 13)),
        (datetime(2026, 9, 6, 12), 200),
    ],
)
def test_invalid_session_time_is_rejected(issued: object, expires: object) -> None:
    with pytest.raises(ValueError):
        UserSession(token_digest="a" * 64, user_id=UserId(uuid7()), issued_at=cast(datetime, issued), expires_at=cast(datetime, expires))


@pytest.mark.parametrize("now", [datetime(2026, 9, 6, 12, tzinfo=UTC), 100])
def test_session_rejects_invalid_comparison_clock(now: object) -> None:
    session = UserSession(
        token_digest="a" * 64,
        user_id=UserId(uuid7()),
        issued_at=datetime(2026, 9, 6, 12),
        expires_at=datetime(2026, 9, 6, 13),
    )
    with pytest.raises(ValueError, match="本地无时区"):
        session.is_valid(now=cast(datetime, now))


@pytest.mark.parametrize("value", [0, -1, 2_592_001])
def test_auth_config_rejects_invalid_ttl(value: int) -> None:
    with pytest.raises(ValidationError):
        AuthSettings(session_ttl_seconds=value, _env_file=None)


def test_auth_config_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_SESSION_TTL_SECONDS", "90")
    assert AuthSettings(_env_file=None).session_ttl_seconds == 90
    with pytest.raises(InvalidCredentialsError):
        LoginCommand(username="alice", password="x" * 1025)


@pytest.mark.asyncio
async def test_user_and_session_share_transaction_and_foreign_key_cascades() -> None:
    databases = DatabaseManager(DatabaseSettings(_env_file=None, connections={"main": {"driver": "sqlite", "database": ":memory:"}}))
    try:
        engine = await databases.get_engine("main")
        async with engine.begin() as connection:
            await connection.run_sync(load_main_database_metadata().create_all)
            assert await connection.scalar(text("PRAGMA foreign_keys")) == 1
        user = User.create(username="alice", email="alice@example.com", password_hash=PasswordHash("test-hash"), now=datetime.now())
        stored = UserSession(
            token_digest="a" * 64,
            user_id=user.id,
            issued_at=datetime(2026, 9, 6, 12),
            expires_at=datetime(2026, 9, 6, 13),
        )

        async with SqlAlchemyUserUnitOfWork(databases, "main") as uow:
            await uow.users.add(user)
            await uow.commit()
        with pytest.raises(RuntimeError, match="rollback"):
            async with SqlAlchemyUserUnitOfWork(databases, "main") as uow:
                await uow.sessions.add(stored)
                # 查询触发真实 INSERT，再模拟事务失败。
                assert await uow.sessions.find(stored.token_digest) == stored
                raise RuntimeError("rollback")
        async with SqlAlchemyUserUnitOfWork(databases, "main") as uow:
            assert await uow.sessions.find(stored.token_digest) is None
            await uow.sessions.add(stored)
            await uow.commit()
        async with SqlAlchemyUserUnitOfWork(databases, "main") as uow:
            assert await uow.sessions.find(stored.token_digest) == stored
            await uow.users.remove(user.id)
            await uow.commit()
        async with databases.session("main") as session:
            assert await session.get(UserSessionModel, stored.token_digest) is None
    finally:
        await databases.aclose()
