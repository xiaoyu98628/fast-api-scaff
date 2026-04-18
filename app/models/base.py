"""SQLAlchemy 声明式基类。"""

from sqlalchemy.orm import DeclarativeBase, declared_attr

from config.config import get_config


class Base(DeclarativeBase):
    """ORM 基类；表名默认 ``{database.prefix}{__tablename_suffix__}``。"""

    @declared_attr.directive
    def __tablename__(cls) -> str:
        if cls.__dict__.get("__abstract__"):
            return f"_abstract_{cls.__name__.lower()}"
        if "__tablename__" in cls.__dict__ and isinstance(cls.__dict__["__tablename__"], str):
            return cls.__dict__["__tablename__"]
        suffix = cls.__dict__.get("__tablename_suffix__")
        if suffix is None:
            raise TypeError(
                f"{cls.__qualname__} 请设置 __tablename_suffix__ = '...'，"
                f"或在本类中声明 __tablename__ = '...'"
            )
        return f"{get_config().database.prefix}{suffix}"
