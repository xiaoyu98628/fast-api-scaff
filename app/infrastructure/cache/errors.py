class CacheError(RuntimeError):
    """缓存基础能力异常基类。"""


class CacheConfigurationError(CacheError):
    """缓存配置缺失或不合法。"""


class CacheConnectionError(CacheError):
    """缓存服务不可连接或健康检查失败。"""


class CacheOperationError(CacheError):
    """缓存读写操作执行失败。"""


class CacheKeyError(CacheError, ValueError):
    """缓存 key 不符合跨驱动约束。"""
