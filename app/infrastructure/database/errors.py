"""定义数据库基础设施对外暴露的稳定异常类型。"""

from sqlalchemy.exc import DisconnectionError, InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError


class DatabaseError(RuntimeError):
    """数据库基础能力异常基类。"""


class DatabaseConfigurationError(DatabaseError):
    """数据库连接配置缺失或不合法。"""


class DatabaseDriverError(DatabaseError):
    """数据库驱动未安装或无法加载。"""


class DatabaseOperationError(DatabaseError):
    """数据库连接、连接池或语句执行阶段发生运行故障。"""


def translate_database_error(error: Exception) -> DatabaseOperationError | None:
    """把可预期的 SQLAlchemy 运行故障转换为不泄漏驱动细节的稳定异常。"""

    if isinstance(error, (DisconnectionError, InterfaceError, OperationalError, SQLAlchemyTimeoutError)):
        return DatabaseOperationError("数据库操作失败")
    return None
