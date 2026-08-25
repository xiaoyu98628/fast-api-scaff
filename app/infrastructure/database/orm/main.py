from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase, declared_attr

from app.config.database import DatabaseSettings
from app.infrastructure.database.connection import resolve_database_table_prefix
from app.infrastructure.database.orm.naming import CONSTRAINT_NAMING_CONVENTION

MAIN_CONNECTION_NAME = "main"
MAIN_TABLE_PREFIX = resolve_database_table_prefix(
    DatabaseSettings(),
    MAIN_CONNECTION_NAME,
)


def main_table_name(name: str) -> str:
    """构建 main 数据库中的完整表名。"""
    return f"{MAIN_TABLE_PREFIX}{name}"


class MainBase(DeclarativeBase):
    """main 数据库 SQLAlchemy ORM 模型的声明基类。"""

    metadata = MetaData(naming_convention=CONSTRAINT_NAMING_CONVENTION)

    @declared_attr.directive
    def __tablename__(cls) -> str:  # noqa: N805
        table_name = cls.__dict__.get("__table_name__")

        if not isinstance(table_name, str) or not table_name:
            raise TypeError(f"{cls.__name__} 必须声明非空的 __table_name__")

        return main_table_name(table_name)
