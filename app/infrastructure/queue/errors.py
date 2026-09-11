"""定义队列基础设施与 Worker 共用的稳定异常类型。"""


class QueueError(Exception):
    """队列公开运行错误。"""


class QueueConfigurationError(QueueError):
    """队列连接、任务定义或运行参数不合法。"""

    pass


class InvalidMessageError(QueueError):
    """消息信封或业务 payload 无法按约定编码、解码。"""

    pass


class JobDecodeError(InvalidMessageError):
    """业务任务 payload 不符合对应 Job 版本的消息契约。"""

    pass


class JobResolutionError(QueueError):
    """Worker 无法把消息中的任务引用解析为可执行 Job。"""

    pass


class UnknownJobError(JobResolutionError):
    """消息引用的 Job 类型不存在或不在允许范围内。"""

    pass


class UnsupportedJobVersionError(JobResolutionError):
    """Job 类型存在，但消息版本不在其兼容范围内。"""

    pass


class JobDefinitionError(QueueError):
    """已部署 Job 的 Codec、Policy、导入依赖或类型声明不合法。"""

    pass


class DeliveryLostError(QueueError):
    """当前消费者已经失去消息所有权，不能继续确认。"""

    pass


class RetryableJobError(QueueError):
    """Worker 适配器可将暂时性业务错误转换为此错误。"""
