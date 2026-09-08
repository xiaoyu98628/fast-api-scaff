"""定义队列消费和消息确认的最小公共契约。"""

from typing import Protocol


class Delivery(Protocol):
    """表示一条尚未确认、可能被后端重新投递的消息。"""

    @property
    def payload(self) -> bytes: ...
    @property
    def identity(self) -> str: ...
    async def acknowledge(self) -> None: ...


class QueueConsumer(Protocol):
    """按后端语义接收消息，并负责释放消费资源。"""

    async def receive(self) -> Delivery: ...
    async def aclose(self) -> None: ...
