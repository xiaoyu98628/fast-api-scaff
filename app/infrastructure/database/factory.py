import logging

from sqlalchemy.exc import NoSuchModuleError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.database.contracts.provider import DatabaseResourceDefinition
from app.infrastructure.database.errors import DatabaseDriverError
from app.infrastructure.database.logging import DatabaseLogEvent, configure_database_logging
from app.infrastructure.database.resource import DatabaseResource

_DATABASE_LOGGER = logging.getLogger("app.infrastructure.database")


async def create_database_resource(connection_name: str, definition: DatabaseResourceDefinition) -> DatabaseResource:
    """创建异步 Engine 和 Session 工厂，不主动建立数据库连接。"""
    spec = definition.engine_spec

    try:
        engine = create_async_engine(spec.url, hide_parameters=True, **dict(spec.options))
    except (ImportError, ModuleNotFoundError, NoSuchModuleError) as error:
        _DATABASE_LOGGER.exception(
            "Database resource creation failed",
            extra={
                "event": DatabaseLogEvent.RESOURCE_CREATE_FAILED,
                "details": {
                    "connection": connection_name,
                    "driver": spec.url.drivername,
                },
            },
        )
        raise DatabaseDriverError(f"数据库驱动 {spec.url.drivername!r} 无法加载") from error

    configure_database_logging(engine, connection_name=connection_name, spec=spec)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    _DATABASE_LOGGER.info(
        "Database resource created",
        extra={
            "event": DatabaseLogEvent.RESOURCE_CREATED,
            "details": {
                "connection": connection_name,
                "driver": spec.url.drivername,
            },
        },
    )

    return DatabaseResource(connection_name=connection_name, engine=engine, session_factory=session_factory)


async def close_database_resource(resource: DatabaseResource) -> None:
    try:
        await resource.engine.dispose()
    except Exception:
        _DATABASE_LOGGER.exception(
            "Database resource close failed",
            extra={
                "event": DatabaseLogEvent.RESOURCE_CLOSE_FAILED,
                "details": {
                    "connection": resource.connection_name,
                    "driver": resource.engine.url.drivername,
                },
            },
        )
        raise

    _DATABASE_LOGGER.info(
        "Database resource closed",
        extra={
            "event": DatabaseLogEvent.RESOURCE_CLOSED,
            "details": {
                "connection": resource.connection_name,
                "driver": resource.engine.url.drivername,
            },
        },
    )
