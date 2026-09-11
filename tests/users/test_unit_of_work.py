"""验证用户工作单元的事务清理和冲突转换。"""

import sqlite3
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import cast

import pytest
from asyncmy.errors import IntegrityError as MySQLIntegrityError
from asyncpg.exceptions._base import PostgresError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import DatabaseSettings
from app.contexts.user.application.dto import CreateUserCommand
from app.contexts.user.application.errors import UserConflictError
from app.contexts.user.composition import build_user_context
from app.contexts.user.domain.user import User
from app.contexts.user.domain.values import PasswordHash
from app.contexts.user.infrastructure.persistence.models.user import UserModel
from app.contexts.user.infrastructure.persistence.unit_of_work import SqlAlchemyUserUnitOfWork, _resolve_user_conflict_field
from app.infrastructure.database.manager import DatabaseManager


@pytest.mark.asyncio
async def test_user_context_binds_unit_of_work_to_main_connection() -> None:
    databases = DatabaseManager(
        DatabaseSettings(
            default="fallback",
            connections={
                "main": {"driver": "sqlite", "database": ":memory:"},
                "fallback": {"driver": "sqlite", "database": ":memory:"},
            },
            _env_file=None,
        )
    )
    engine = await databases.get_engine("main")
    async with engine.begin() as connection:
        await connection.run_sync(UserModel.metadata.create_all)

    users = build_user_context(databases)
    created = await users.service.create(
        CreateUserCommand(
            username="alice",
            email="alice@example.com",
            password="password123",
        )
    )

    assert created.username == "alice"
    assert databases.is_initialized("main") is True
    assert databases.is_initialized("fallback") is False
    await databases.aclose()


def sqlite_error(message: str, code: int) -> sqlite3.IntegrityError:
    error = sqlite3.IntegrityError(message)
    error.sqlite_errorcode = code
    return error


def postgresql_error(*, constraint: str, unique: bool = True, table: str = "users", wrapped: bool = False) -> Exception:
    error = PostgresError.new(
        {
            "C": "23505" if unique else "23502",
            "M": "value contains uq_users_username and uq_users_email",
            "n": constraint,
            "t": table,
        }
    )
    if wrapped:
        wrapper = Exception("SQLAlchemy asyncpg adapter")
        wrapper.__cause__ = error
        return wrapper
    return error


@pytest.mark.parametrize(
    ("original", "expected"),
    [
        (sqlite_error("UNIQUE constraint failed: users.username", sqlite3.SQLITE_CONSTRAINT_UNIQUE), "username"),
        (sqlite_error("UNIQUE constraint failed: users.email", sqlite3.SQLITE_CONSTRAINT_UNIQUE), "email"),
        (postgresql_error(constraint="uq_users_email", wrapped=True), "email"),
        (postgresql_error(constraint="users_username_key"), "username"),
        (MySQLIntegrityError(1062, "Duplicate entry 'alice' for key 'users.uq_users_username'"), "username"),
        (MySQLIntegrityError(1062, "Duplicate entry 'uq_users_username@example.com' for key 'uq_users_email'"), "email"),
        (MySQLIntegrityError(1062, "Duplicate entry 'x for key 'uq_users_username'' for key 'users.uq_users_email'"), "email"),
    ],
)
def test_user_unit_of_work_recognizes_known_unique_constraints(original: Exception, expected: str) -> None:
    assert _resolve_user_conflict_field(IntegrityError("INSERT", {}, original)) == expected


@pytest.mark.parametrize(
    "original",
    [
        sqlite_error("NOT NULL constraint failed: users.username", sqlite3.SQLITE_CONSTRAINT_NOTNULL),
        sqlite_error("CHECK constraint failed: users.email", sqlite3.SQLITE_CONSTRAINT_CHECK),
        sqlite_error("FOREIGN KEY constraint failed", sqlite3.SQLITE_CONSTRAINT_FOREIGNKEY),
        sqlite_error("UNIQUE constraint failed: users.id", sqlite3.SQLITE_CONSTRAINT_PRIMARYKEY),
        sqlite_error("UNIQUE constraint failed: other.username", sqlite3.SQLITE_CONSTRAINT_UNIQUE),
        sqlite_error("UNIQUE constraint failed: users.username, users.email", sqlite3.SQLITE_CONSTRAINT_UNIQUE),
        postgresql_error(constraint="uq_users_username", unique=False),
        postgresql_error(constraint="unknown_unique"),
        postgresql_error(constraint="uq_users_username", table="other"),
        MySQLIntegrityError(1048, "Column 'users.username' cannot be null"),
        MySQLIntegrityError(1062, "Duplicate entry 'uq_users_username' for key 'unknown_unique'"),
        MySQLIntegrityError(1062, "Duplicate entry 'alice' for key 'other.uq_users_username'"),
        Exception("UNIQUE constraint failed: users.username"),
    ],
)
def test_user_unit_of_work_does_not_translate_unknown_integrity_errors(original: Exception) -> None:
    assert _resolve_user_conflict_field(IntegrityError("INSERT", {}, original)) is None


@pytest.mark.parametrize("integrity_failure", [False, True])
@pytest.mark.asyncio
async def test_user_unit_of_work_closes_session_context_when_rollback_fails(integrity_failure: bool) -> None:
    events: list[str] = []
    original_error = (
        IntegrityError("UPDATE", {}, Exception("UNIQUE constraint failed: users.username")) if integrity_failure else RuntimeError("use case failed")
    )
    rollback_error = RuntimeError("rollback failed")

    class FailingRollbackSession:
        async def rollback(self) -> None:
            events.append("rollback")
            raise rollback_error

    class RecordingSessionContext:
        async def __aenter__(self) -> AsyncSession:
            raise AssertionError("context is already entered")

        async def __aexit__(self, *_args: object) -> None:
            events.append("exit")

    unit_of_work = SqlAlchemyUserUnitOfWork(
        DatabaseManager(DatabaseSettings(_env_file=None)),
        connection_name="main",
    )
    unit_of_work._session = cast(AsyncSession, FailingRollbackSession())
    unit_of_work._session_context = cast(AbstractAsyncContextManager[AsyncSession], RecordingSessionContext())

    with pytest.raises(ExceptionGroup) as captured_error:
        await unit_of_work.__aexit__(type(original_error), original_error, None)

    assert events == ["rollback", "exit"]
    assert captured_error.value.exceptions == (original_error, rollback_error)
    assert unit_of_work._session is None
    assert unit_of_work._session_context is None


@pytest.mark.parametrize("stage", ["insert", "update"])
@pytest.mark.parametrize("field", ["username", "email"])
@pytest.mark.asyncio
async def test_unique_conflicts_are_translated_and_rolled_back(stage: str, field: str) -> None:
    databases = DatabaseManager(DatabaseSettings(_env_file=None, connections={"main": {"driver": "sqlite", "database": ":memory:"}}))
    first = User.create(username="alice", email="alice@example.com", password_hash=PasswordHash("test-hash"), now=datetime.now())
    second = User.create(username="bobby", email="bobby@example.com", password_hash=PasswordHash("test-hash"), now=datetime.now())
    try:
        engine = await databases.get_engine("main")
        async with engine.begin() as connection:
            await connection.run_sync(UserModel.metadata.create_all)
        async with SqlAlchemyUserUnitOfWork(databases, "main") as unit_of_work:
            await unit_of_work.users.add(first)
            await unit_of_work.users.add(second)
            await unit_of_work.commit()

        username = "alice" if field == "username" else "third"
        email = "alice@example.com" if field == "email" else "third@example.com"
        with pytest.raises(UserConflictError) as captured:
            async with SqlAlchemyUserUnitOfWork(databases, "main") as unit_of_work:
                if stage == "insert":
                    duplicate = User.create(username=username, email=email, password_hash=PasswordHash("test-hash"), now=datetime.now())
                    await unit_of_work.users.add(duplicate)
                    await unit_of_work.commit()
                else:
                    second.update_profile(username=username, email=email, now=datetime.now())
                    await unit_of_work.users.update(second)
                pytest.fail("The conflicting write must raise immediately")

        assert captured.value.field == field
        assert isinstance(captured.value.__cause__, IntegrityError)
        assert unit_of_work._session is None
        async with SqlAlchemyUserUnitOfWork(databases, "main") as unit_of_work:
            stored = await unit_of_work.users.find(second.id)
            _, total = await unit_of_work.users.find_page(offset=0, limit=20)
        assert stored is not None
        assert stored.username.value == "bobby"
        assert stored.email.value == "bobby@example.com"
        assert total == 2
    finally:
        await databases.aclose()


@pytest.mark.asyncio
async def test_transaction_exit_preserves_unknown_integrity_error() -> None:
    databases = DatabaseManager(DatabaseSettings(_env_file=None, connections={"main": {"driver": "sqlite", "database": ":memory:"}}))
    original = IntegrityError("UPDATE", {}, Exception("CHECK constraint failed: ck_users_status"))
    try:
        with pytest.raises(IntegrityError) as captured:
            async with SqlAlchemyUserUnitOfWork(databases, "main") as unit_of_work:
                raise original
        assert captured.value is original
        assert unit_of_work._session is None
    finally:
        await databases.aclose()


@pytest.mark.asyncio
async def test_commit_preserves_integrity_error_when_rollback_fails() -> None:
    original = IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed: users.email"))
    cleanup = RuntimeError("rollback failed")

    class FailingSession:
        async def commit(self) -> None:
            raise original

        async def rollback(self) -> None:
            raise cleanup

    unit_of_work = SqlAlchemyUserUnitOfWork(DatabaseManager(DatabaseSettings(_env_file=None)), "main")
    unit_of_work._session = cast(AsyncSession, FailingSession())
    with pytest.raises(ExceptionGroup) as captured:
        await unit_of_work.commit()
    assert captured.value.exceptions == (original, cleanup)


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO users (id) VALUES ('missing-fields')",
        "INSERT INTO users (id, username, email, password, status, created_at, updated_at) "
        "VALUES ('bad-status', 'alice', 'alice@example.com', 'test-hash', 'invalid', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
    ],
)
@pytest.mark.asyncio
async def test_real_sqlite_internal_constraint_errors_are_not_business_conflicts(statement: str) -> None:
    databases = DatabaseManager(DatabaseSettings(_env_file=None, connections={"main": {"driver": "sqlite", "database": ":memory:"}}))
    try:
        engine = await databases.get_engine("main")
        async with engine.begin() as connection:
            await connection.run_sync(UserModel.metadata.create_all)
        with pytest.raises(IntegrityError) as captured:
            async with SqlAlchemyUserUnitOfWork(databases, "main") as unit_of_work:
                assert unit_of_work._session is not None
                await unit_of_work._session.execute(text(statement))
        assert isinstance(captured.value.orig, sqlite3.IntegrityError)
        assert unit_of_work._session is None
    finally:
        await databases.aclose()
