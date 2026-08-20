class CacheError(RuntimeError):
    """缓存基础能力异常基类。"""


class CacheConfigurationError(CacheError):
    """缓存连接配置缺失或不合法。"""
