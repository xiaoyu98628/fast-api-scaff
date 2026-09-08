"""定义队列后端需要实现的发布、消费与关闭能力。"""

from typing import Protocol

from app.infrastructure.queue.contracts.consumer import QueueConsumer


class QueueBackend(Protocol):
    """屏蔽 Redis、Kafka 和 RabbitMQ 的协议差异。"""

    async def publish(self, queue: str, payload: bytes) -> None: ...
    async def consumer(self, queue: str, concurrency: int) -> QueueConsumer: ...
    async def aclose(self) -> None: ...
