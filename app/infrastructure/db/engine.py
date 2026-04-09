"""异步数据库引擎的创建与销毁（单进程内懒加载单例）。"""

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from config.config import get_config

_engine: AsyncEngine | None = None


def get_engine() -> AsyncEngine | None:
    """首次调用时根据配置创建 ``AsyncEngine``，后续复用同一实例。"""
    global _engine
    if _engine is None:
        database_config = get_config().database
        _engine = create_async_engine(
            database_config.url,
            pool_pre_ping=True,
            echo=database_config.echo,
            pool_size=database_config.pool_size,
            max_overflow=database_config.max_overflow,
        )
    return _engine


async def dispose_engine() -> None:
    """关闭连接池并清空模块级引擎引用（通常在应用 shutdown 时调用）。"""
    global _engine
    if _engine is not None:
        await _engine.dispose()
    _engine = None
