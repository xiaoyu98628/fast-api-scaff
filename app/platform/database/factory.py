from sqlalchemy import URL
from sqlalchemy.exc import NoSuchModuleError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config.database import (
    DatabaseConnectionSettings,
    MySQLConnectionSettings,
    PostgreSQLConnectionSettings,
    SQLiteConnectionSettings,
)
from app.platform.database.errors import DatabaseDriverError
from app.platform.database.resource import DatabaseResource


async def create_database_resource(settings: DatabaseConnectionSettings) -> DatabaseResource:
    """创建异步 Engine 和 Session 工厂，不主动建立数据库连接。"""

    engine_options: dict[str, object] = {"echo": settings.echo}

    match settings:
        case MySQLConnectionSettings():
            url = URL.create(
                drivername="mysql+asyncmy",
                username=settings.username,
                password=settings.password.get_secret_value(),
                host=settings.host,
                port=settings.port,
                database=settings.database,
                query={"charset": settings.charset},
            )
            engine_options.update(
                pool_size=settings.pool_size,
                max_overflow=settings.max_overflow,
                pool_pre_ping=settings.pool_pre_ping,
                pool_recycle=settings.pool_recycle,
            )
        case PostgreSQLConnectionSettings():
            url = URL.create(
                drivername="postgresql+asyncpg",
                username=settings.username,
                password=settings.password.get_secret_value(),
                host=settings.host,
                port=settings.port,
                database=settings.database,
            )
            engine_options.update(
                pool_size=settings.pool_size,
                max_overflow=settings.max_overflow,
                pool_pre_ping=settings.pool_pre_ping,
                pool_recycle=settings.pool_recycle,
            )
        case SQLiteConnectionSettings():
            url = URL.create(
                drivername="sqlite+aiosqlite",
                database=settings.resolved_database,
            )

    try:
        engine = create_async_engine(url, **engine_options)
    except (ImportError, ModuleNotFoundError, NoSuchModuleError) as error:
        raise DatabaseDriverError(f"数据库驱动 {url.drivername!r} 无法加载") from error

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    return DatabaseResource(engine=engine, session_factory=session_factory)


async def close_database_resource(resource: DatabaseResource) -> None:
    await resource.engine.dispose()
