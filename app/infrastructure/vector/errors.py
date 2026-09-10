"""定义向量存储配置、资源和操作的稳定异常边界。"""


class VectorError(Exception):
    """向量存储公共异常基类。"""


class VectorConfigurationError(VectorError):
    """向量连接、集合或查询参数不合法。"""


class VectorConnectionError(VectorError):
    """向量服务不可访问或客户端无法建立连接。"""


class VectorOperationError(VectorError):
    """向量存储操作失败且无法映射为更具体的异常。"""


class VectorCollectionNotFoundError(VectorOperationError):
    """目标 Collection 或 Elasticsearch Index 不存在。"""


class VectorCollectionConflictError(VectorOperationError):
    """创建的 Collection 或 Index 已经存在。"""
