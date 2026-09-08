"""定义队列基础设施与 Worker 共用的稳定异常类型。"""


class QueueError(Exception):
    """队列公开运行错误。"""


class QueueConfigurationError(QueueError):
    """队列连接、任务定义或运行参数不合法。"""

    pass


class InvalidMessageError(QueueError):
    """消息信封或业务 payload 无法按约定编码、解码。"""

    pass


class DeliveryLostError(QueueError):
    """当前消费者已经失去消息所有权，不能继续确认。"""

    pass


class RetryableJobError(QueueError):
    """Worker 适配器可将暂时性业务错误转换为此错误。"""
