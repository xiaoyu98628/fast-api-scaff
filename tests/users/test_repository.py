from datetime import UTC, datetime

import pytest

from app.config.database import DatabaseSettings
from app.contexts.user.domain.user import User
from app.contexts.user.domain.values import EmailAddress, UserId, Username, UserStatus
from app.contexts.user.infrastructure.persistence.model import UserRecord
from app.contexts.user.infrastructure.persistence.repository import SqlAlchemyUserRepository
from app.infrastructure.database.manager import DatabaseManager


@pytest.mark.asyncio
async def test_sqlalchemy_user_repository_persists_and_queries_users() -> None:
    manager = DatabaseManager(
        DatabaseSettings(
            default="main",
            connections={"main": {"driver": "sqlite", "database": ":memory:"}},
            _env_file=None,
        )
    )
    engine = await manager.get_engine()
    async with engine.begin() as connection:
        await connection.run_sync(UserRecord.metadata.create_all)

    now = datetime(2026, 8, 28, tzinfo=UTC)
    user = User.create(username="alice", email="alice@example.com", display_name="Alice", now=now)

    async with manager.session() as session:
        repository = SqlAlchemyUserRepository(session)
        await repository.add(user)
        await session.commit()

        found = await repository.find(user.id)
        users, total = await repository.find_page(offset=0, limit=20)

        assert found is not None
        assert found.username == Username("alice")
        assert users == [found]
        assert total == 1
        assert await repository.exists_by_email(EmailAddress("alice@example.com")) is True

        found.update_profile(
            username="alice_new",
            email="new@example.com",
            display_name="Alice New",
            status=UserStatus.DISABLED,
            now=now,
        )
        await repository.update(found)
        await session.commit()

        updated = await repository.find(user.id)
        assert updated is not None
        assert updated.status is UserStatus.DISABLED

        await repository.remove(UserId(user.id.value))
        await session.commit()
        assert await repository.find(user.id) is None

    await manager.aclose()
