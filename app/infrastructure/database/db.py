from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.manager import get_manager
from config.database import DbDriver


class DB:
    """数据库 Facade，提供统一的连接入口。"""

    @staticmethod
    @asynccontextmanager
    async def connection(name: DbDriver | str | None = None) -> AsyncGenerator[AsyncSession, None]:
        async with get_manager().connection(name).session() as session:
            yield session
