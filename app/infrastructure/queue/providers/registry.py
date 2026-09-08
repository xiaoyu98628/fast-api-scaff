"""根据严格队列连接配置选择对应后端实现。"""

from app.config.queue import KafkaQueueSettings, QueueConnection, RabbitMQQueueSettings, RedisQueueSettings
from app.infrastructure.queue.contracts.provider import QueueBackend
from app.infrastructure.queue.drivers.kafka import KafkaBackend
from app.infrastructure.queue.drivers.rabbitmq import RabbitBackend
from app.infrastructure.queue.drivers.redis import RedisBackend


async def create_backend(settings: QueueConnection) -> QueueBackend:
    """构建配置类型对应的 Redis、Kafka 或 RabbitMQ 后端。"""

    match settings:
        case RedisQueueSettings():
            return RedisBackend(settings)
        case KafkaQueueSettings():
            return await KafkaBackend.create(settings)
        case RabbitMQQueueSettings():
            return await RabbitBackend.create(settings)
