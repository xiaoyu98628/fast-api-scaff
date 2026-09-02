from contextlib import AbstractAsyncContextManager
from typing import cast

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import DatabaseSettings
from app.contexts.user.application.dto import CreateUserCommand
from app.contexts.user.composition import build_user_context
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
            display_name="Alice",
        )
    )

    assert created.username == "alice"
    assert databases.is_initialized("main") is True
    assert databases.is_initialized("fallback") is False
    await databases.aclose()


@pytest.mark.parametrize(
    ("details", "expected"),
    [
        ("UNIQUE constraint failed: users.username", "username"),
        ('duplicate key value violates unique constraint "uq_users_email"', "email"),
        ("duplicate entry for key users_username_key", "username"),
    ],
)
def test_user_unit_of_work_recognizes_known_unique_constraints(details: str, expected: str) -> None:
    error = IntegrityError("INSERT", {}, Exception(details))

    assert _resolve_user_conflict_field(error) == expected


def test_user_unit_of_work_does_not_translate_unknown_integrity_errors() -> None:
    error = IntegrityError("INSERT", {}, Exception("CHECK constraint failed: ck_users_status"))

    assert _resolve_user_conflict_field(error) is None


@pytest.mark.asyncio
async def test_user_unit_of_work_closes_session_context_when_rollback_fails() -> None:
    events: list[str] = []
    original_error = RuntimeError("use case failed")
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
        await unit_of_work.__aexit__(RuntimeError, original_error, None)

    assert events == ["rollback", "exit"]
    assert captured_error.value.exceptions == (original_error, rollback_error)
    assert unit_of_work._session is None
    assert unit_of_work._session_context is None
