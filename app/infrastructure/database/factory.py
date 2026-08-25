from sqlalchemy.exc import NoSuchModuleError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config.database import DatabaseConnectionSettings
from app.infrastructure.database.engine import build_database_engine_spec
from app.infrastructure.database.errors import DatabaseDriverError
from app.infrastructure.database.resource import DatabaseResource


async def create_database_resource(settings: DatabaseConnectionSettings) -> DatabaseResource:
    """创建异步 Engine 和 Session 工厂，不主动建立数据库连接。"""
    spec = build_database_engine_spec(settings)

    try:
        engine = create_async_engine(spec.url, **dict(spec.options))
    except (ImportError, ModuleNotFoundError, NoSuchModuleError) as error:
        raise DatabaseDriverError(f"数据库驱动 {spec.url.drivername!r} 无法加载") from error

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    return DatabaseResource(engine=engine, session_factory=session_factory)


async def close_database_resource(resource: DatabaseResource) -> None:
    await resource.engine.dispose()
