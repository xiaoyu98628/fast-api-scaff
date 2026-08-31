import pytest

from app.config.database import DatabaseSettings
from app.contexts.user.application.dto import CreateUserCommand
from app.contexts.user.composition import build_user_context
from app.contexts.user.infrastructure.persistence.models.user import UserModel
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
