from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.database_manager import get_database_manager
from config.database import DbDriver


class DB:
    """数据库 Facade（对应 Laravel Support\\Facades\\DB）。"""

    @staticmethod
    @asynccontextmanager
    async def connection(name: DbDriver | str | None = None) -> AsyncGenerator[AsyncSession, None]:
        conn = get_database_manager().connection(name)
        async with conn.session() as session:
            yield session
