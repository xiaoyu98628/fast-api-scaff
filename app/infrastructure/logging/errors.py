"""定义日志配置阶段的领域异常。"""


class LoggingConfigurationError(ValueError):
    """日志配置无法解析或引用了不可用的驱动。"""
