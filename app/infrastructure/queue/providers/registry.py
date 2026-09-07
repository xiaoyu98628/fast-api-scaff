from app.config.queue import KafkaQueueSettings, QueueConnection, RabbitMQQueueSettings, RedisQueueSettings
from app.infrastructure.queue.contracts.provider import QueueBackend
from app.infrastructure.queue.drivers.kafka import KafkaBackend
from app.infrastructure.queue.drivers.rabbitmq import RabbitBackend
from app.infrastructure.queue.drivers.redis import RedisBackend


async def create_backend(settings: QueueConnection) -> QueueBackend:
    match settings:
        case RedisQueueSettings():
            return RedisBackend(settings)
        case KafkaQueueSettings():
            return await KafkaBackend.create(settings)
        case RabbitMQQueueSettings():
            return await RabbitBackend.create(settings)
