"""显式注册 main 数据库迁移需要发现的全部 ORM Model。"""

from sqlalchemy import MetaData

from app.contexts.user.infrastructure.persistence.models.session import UserSessionModel
from app.contexts.user.infrastructure.persistence.models.user import UserModel
from app.infrastructure.database.orm.main import MainBase
from app.infrastructure.queue.failed.sql.model import FailedJobModel

_MAIN_DATABASE_MODELS: tuple[type[MainBase], ...] = (FailedJobModel, UserModel, UserSessionModel)


def load_main_database_metadata() -> MetaData:
    """加载 main 数据库 ORM Model 并返回 Alembic 使用的 Metadata。"""

    # 显式列表避免 Alembic 依赖目录扫描或偶然的导入副作用发现模型。
    for model in _MAIN_DATABASE_MODELS:
        if model.metadata is not MainBase.metadata:
            raise RuntimeError(f"{model.__name__} 没有注册到 MainBase.metadata")

    return MainBase.metadata
