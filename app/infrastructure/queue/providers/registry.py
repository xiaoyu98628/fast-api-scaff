"""根据严格队列连接配置选择对应后端实现。"""

from app.config.queue import KafkaQueueSettings, QueueConnection, RabbitMQQueueSettings, RedisQueueSettings
from app.infrastructure.queue.contracts.provider import QueueBackend
from app.infrastructure.queue.errors import QueueConfigurationError


async def create_backend(settings: QueueConnection) -> QueueBackend:
    """只导入并构建当前配置对应的队列后端。"""

    try:
        match settings:
            case RedisQueueSettings():
                from app.infrastructure.queue.drivers.redis import RedisBackend

                return RedisBackend(settings)
            case KafkaQueueSettings():
                from app.infrastructure.queue.drivers.kafka import KafkaBackend

                return await KafkaBackend.create(settings)
            case RabbitMQQueueSettings():
                from app.infrastructure.queue.drivers.rabbitmq import RabbitBackend

                return await RabbitBackend.create(settings)
    except ModuleNotFoundError as error:
        # 驱动包缺失是部署配置问题，不能伪装成远端服务连接失败。
        driver = settings.driver
        raise QueueConfigurationError(f"队列驱动 {driver!r} 的客户端依赖无法加载") from error

    raise AssertionError(f"未知队列连接配置类型: {type(settings)!r}")
