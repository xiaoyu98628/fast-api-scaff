"""SQLAlchemy 声明式基类；Alembic ``target_metadata`` 通常指向 ``Base.metadata``。"""

from sqlalchemy.orm import DeclarativeBase, declared_attr

from config.config import get_config


class Base(DeclarativeBase):
    """所有 ORM 模型的基类，继承后映射到具体表（定义在 models 包）。

    表名默认 ``{database.prefix}{__tablename_suffix__}``。子类设置 ``__tablename_suffix__``
    即可（如 ``"users"``）。需要全表名自定时可写 ``__tablename__ = "..."`` 覆盖。

    仅作列/关系复用的抽象父类请设 ``__abstract__ = True``；判断抽象类时必须写在
    **本类** ``__dict__`` 里，勿依赖 ``getattr(..., "__abstract__")``（会从父类继承误判）。
    """

    @declared_attr.directive
    def __tablename__(cls) -> str:
        # 必须用 cls.__dict__，否则子类会继承到父类的 __abstract__=True
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
