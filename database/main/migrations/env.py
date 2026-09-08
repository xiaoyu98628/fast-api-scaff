"""配置 main 数据库的 Alembic 离线和异步在线迁移环境。"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app.config.database import DatabaseSettings
from app.infrastructure.database.connections.resolver import resolve_database_definition
from app.infrastructure.database.connections.spec import DatabaseEngineSpec
from database.main.model_registry import load_main_database_metadata

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
# Alembic 在导入 env.py 前注入当前命令对应的 Config。
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
# 迁移进程沿用 alembic.ini 中的日志配置。
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
# 统一通过显式模型注册表提供 autogenerate 所需的完整 metadata。
target_metadata = load_main_database_metadata()

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def load_engine_spec() -> DatabaseEngineSpec:
    """读取当前迁移环境指定的数据库连接。"""
    connection_name = config.get_main_option("connection_name")

    if not connection_name:
        raise RuntimeError("Alembic connection_name 未配置")

    definition = resolve_database_definition(
        DatabaseSettings(),
        connection_name,
    )

    return definition.engine_spec


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    在不建立数据库连接的情况下生成迁移 SQL。
    """

    spec = load_engine_spec()

    context.configure(
        url=spec.url.render_as_string(hide_password=False),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=spec.url.get_backend_name() == "sqlite",
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """把同步 Connection 交给 Alembic 执行当前迁移链。"""

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=connection.dialect.name == "sqlite",
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """通过 SQLAlchemy 异步 Engine 执行迁移。"""

    spec = load_engine_spec()
    # 迁移进程使用一次性连接，不复用应用运行时连接池。
    engine = create_async_engine(spec.url, poolclass=pool.NullPool)

    try:
        async with engine.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await engine.dispose()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.

    从 Alembic 同步入口启动异步迁移事件循环。
    """

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
