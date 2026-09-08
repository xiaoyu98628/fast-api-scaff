"""定义队列后端需要实现的发布、消费与关闭能力。"""

from typing import Protocol

from app.infrastructure.queue.contracts.consumer import QueueConsumer


class QueueBackend(Protocol):
    """屏蔽 Redis、Kafka 和 RabbitMQ 的协议差异。"""

    async def publish(self, queue: str, payload: bytes) -> None:
        """向后端指定逻辑队列发布完整信封字节。"""

        ...

    async def consumer(self, queue: str, concurrency: int) -> QueueConsumer:
        """为逻辑队列创建使用指定并发提示的消费者。"""

        ...

    async def aclose(self) -> None:
        """关闭后端客户端及其持有的网络资源。"""

        ...
