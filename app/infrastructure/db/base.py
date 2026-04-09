"""SQLAlchemy 声明式基类；Alembic ``target_metadata`` 通常指向 ``Base.metadata``。"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """所有 ORM 模型的基类，继承后映射到具体表（定义在 models 包）。"""
