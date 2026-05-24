"""按需会话：Service 内 ``async with SessionProvider().session()`` 使用。"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.db import DB


class SessionProvider:
    """为应用层提供 Lazy Session；写操作用例在成功路径 ``await session.commit()``。"""

    def __init__(self, connection_name: str | None = None) -> None:
        self._connection_name = connection_name

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession]:
        async with DB.connection(self._connection_name) as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
