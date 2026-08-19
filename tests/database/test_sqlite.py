import pytest
from sqlalchemy import text

from app.config.database import DatabaseSettings
from app.platform.database.manager import DatabaseManager


@pytest.mark.asyncio
async def test_sqlite_session_executes_query() -> None:
    settings = DatabaseSettings(
        default="main",
        connections={"main": {"driver": "sqlite", "database": ":memory:"}},
        _env_file=None,
    )
    manager = DatabaseManager(settings)

    async with manager.session() as session:
        result = await session.execute(text("SELECT 1"))

    assert result.scalar_one() == 1
    await manager.aclose()
