from typing import ClassVar

from sqlalchemy.orm import DeclarativeBase, declared_attr

from config.config import config


class Base(DeclarativeBase):
    """ORM 基类：声明连接名与逻辑表名，表前缀由连接配置拼接。"""

    __abstract__ = True

    __connection__: ClassVar[str | None] = None
    __table_name__: ClassVar[str]

    @classmethod
    def connection_name(cls) -> str:
        if cls.__connection__ is not None:
            return cls.__connection__
        return config().database.connection

    @classmethod
    def table_prefix(cls) -> str:
        return config().database.configuration(cls.connection_name()).prefix

    @declared_attr.directive
    def __tablename__(cls) -> str:
        logical_name = cls.__dict__.get("__table_name__")
        if logical_name is None:
            raise TypeError(f"{cls.__name__} must define __table_name__")

        connection = cls.__dict__.get("__connection__")
        connection_name = connection if connection is not None else config().database.connection
        prefix = config().database.configuration(connection_name).prefix
        return f"{prefix}{logical_name}"
