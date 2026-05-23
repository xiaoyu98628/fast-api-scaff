from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


class Connection:
    """连接实例：包装 Engine，提供短生命周期的 Session 上下文。"""

    def __init__(self, name: str, driver: str, engine: AsyncEngine) -> None:
        self._name = name
        self._driver = driver
        self._engine = engine
        self._sessionmaker: async_sessionmaker[AsyncSession] | None = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def driver(self) -> str:
        return self._driver

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        if self._sessionmaker is None:
            self._sessionmaker = async_sessionmaker(self._engine, expire_on_commit=False)

        session = self._sessionmaker()
        try:
            yield session
        finally:
            await session.close()

    async def disconnect(self) -> None:
        await self._engine.dispose()
        self._sessionmaker = None
