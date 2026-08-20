class DatabaseError(RuntimeError):
    """数据库基础能力异常基类。"""


class DatabaseConfigurationError(DatabaseError):
    """数据库连接配置缺失或不合法。"""


class DatabaseDriverError(DatabaseError):
    """数据库驱动未安装或无法加载。"""
