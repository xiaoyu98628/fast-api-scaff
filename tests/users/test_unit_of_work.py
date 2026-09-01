import pytest
from sqlalchemy.exc import IntegrityError

from app.config.database import DatabaseSettings
from app.contexts.user.application.dto import CreateUserCommand
from app.contexts.user.composition import build_user_context
from app.contexts.user.infrastructure.persistence.models.user import UserModel
from app.contexts.user.infrastructure.persistence.unit_of_work import _resolve_user_conflict_field
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
