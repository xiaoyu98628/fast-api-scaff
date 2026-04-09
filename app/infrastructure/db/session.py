"""异步 Session 工厂、依赖注入用的 ``get_db_session``，以及进程退出时的清理。"""

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.db.engine import dispose_engine, get_engine

_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_session_factory() -> async_sessionmaker[AsyncSession] | None:
    """绑定当前引擎的 ``async_sessionmaker``，供业务代码或 ``get_db_session`` 使用。"""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )
    return _session_factory


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：``Depends(get_db_session)`` 获取请求级 Session，异常时回滚。"""
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def ping_db() -> bool:
    """仅检测 TCP/SQL 连通性，不经过 ORM 模型。"""
    engine = get_engine()
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return True


async def close_db() -> None:
    """释放引擎并丢弃 Session 工厂，与 ``app.main`` 中 lifespan 配对。"""
    global _session_factory
    await dispose_engine()
    _session_factory = None
