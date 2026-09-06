from datetime import datetime

import pytest
from sqlalchemy import select

from app.config.database import DatabaseSettings
from app.contexts.user.domain.user import User
from app.contexts.user.domain.values import EmailAddress, PasswordHash, UserId, Username, UserStatus
from app.contexts.user.infrastructure.persistence.models.user import UserModel
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
        await connection.run_sync(UserModel.metadata.create_all)

    now = datetime(2026, 8, 28, 18, 30)
    password_hash = PasswordHash("test-password-hash")
    user = User.create(username="alice", email="alice@example.com", password_hash=password_hash, now=now)

    async with manager.session() as session:
        repository = SqlAlchemyUserRepository(session)
        await repository.add(user)
        await session.commit()

        database_user_id = str(user.id.value)
        stored_id = await session.scalar(select(UserModel.id).where(UserModel.id == database_user_id))
        stored_created_at = await session.scalar(select(UserModel.created_at).where(UserModel.id == database_user_id))

        found = await repository.find(user.id)
        users, total = await repository.find_page(offset=0, limit=20)

        assert found is not None
        assert stored_id == str(found.id.value)
        assert stored_created_at == datetime(2026, 8, 28, 18, 30)
        assert found.created_at == now
        assert found.username == Username("alice")
        assert found.password_hash == password_hash
        assert users == [found]
        assert total == 1
        assert await repository.exists_by_email(EmailAddress("alice@example.com")) is True

        found.update_profile(
            username="alice_new",
            email="new@example.com",
            now=now,
        )
        found.change_status(status=UserStatus.DISABLED, now=now)
        assert await repository.update(found) is True
        await session.commit()

        updated = await repository.find(user.id)
        assert updated is not None
        assert updated.status is UserStatus.DISABLED

        assert await repository.remove(UserId(user.id.value)) is True
        await session.commit()
        assert await repository.find(user.id) is None
        assert await repository.update(found) is False
        assert await repository.remove(UserId(user.id.value)) is False

    await manager.aclose()
