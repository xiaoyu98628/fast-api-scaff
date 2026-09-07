class QueueError(Exception):
    """队列公开运行错误。"""


class QueueConfigurationError(QueueError):
    pass


class InvalidMessageError(QueueError):
    pass


class DeliveryLostError(QueueError):
    pass


class RetryableJobError(QueueError):
    """Worker 适配器可将暂时性业务错误转换为此错误。"""
