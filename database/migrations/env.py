"""
Alembic 运行环境：从项目 ``Config`` 注入同步数据库 URL，``target_metadata`` 对应 ORM ``Base``。

若使用 autogenerate，请在此文件（或下方注释处）import 所有模型模块，以便加载 ``Table`` 到 metadata。
"""

import asyncio
import sys
from pathlib import Path
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Alembic 的运行目录可能与项目根目录不一致，显式把项目根目录加入 sys.path，
# 以保证 `config` / `app` 包能稳定被导入。
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.config import get_config
from app.infrastructure.db.base import Base

# 确保在 autogenerate / upgrade 阶段加载所有模型，避免 Base.metadata 为空导致生成空迁移。
# 这里建议显式 import（当前项目只有 user 模型），后续新增模型再补充 import。
from app.infrastructure.db.models import user as _user_model  # noqa: F401

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config
configs = get_config()
# 使用异步驱动生成 AsyncEngine，避免 async_engine_from_config 加载到 pymysql 这类同步驱动。
config.set_main_option(
    "sqlalchemy.url",
    # SQLAlchemy 的 URL.__str__ 会隐藏密码（***），Alembic 需要真实密码才能鉴权
    configs.database.url.render_as_string(hide_password=False),
)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
