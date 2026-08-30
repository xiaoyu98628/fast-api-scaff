from sqlalchemy import MetaData

from app.contexts.user.infrastructure.persistence.models.user import UserModel
from app.infrastructure.database.orm.main import MainBase

_MAIN_DATABASE_MODELS: tuple[type[MainBase], ...] = (UserModel,)


def load_main_database_metadata() -> MetaData:
    """加载 main 数据库 ORM Model 并返回 Alembic 使用的 Metadata。"""
    for model in _MAIN_DATABASE_MODELS:
        if model.metadata is not MainBase.metadata:
            raise RuntimeError(f"{model.__name__} 没有注册到 MainBase.metadata")

    return MainBase.metadata
