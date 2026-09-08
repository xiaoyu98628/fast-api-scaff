"""定义 main 数据库所有 ORM Model 共用的声明基类。"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

from app.infrastructure.database.orm.naming import CONSTRAINT_NAMING_CONVENTION


class MainBase(DeclarativeBase):
    """main 数据库 SQLAlchemy ORM 模型的声明基类。"""

    metadata = MetaData(naming_convention=CONSTRAINT_NAMING_CONVENTION)
