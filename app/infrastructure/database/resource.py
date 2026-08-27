from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


@dataclass(frozen=True, slots=True)
class DatabaseResource:
    """一个已经创建的异步数据库 Engine 及其 Session 工厂。"""

    connection_name: str
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
