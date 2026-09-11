"""定义队列消费和消息确认的最小公共契约。"""

from typing import Protocol


class Delivery(Protocol):
    """表示一条尚未确认、可能被后端重新投递的消息。"""

    @property
    def payload(self) -> bytes:
        """返回后端交付的完整原始信封字节。"""

        ...

    @property
    def identity(self) -> str:
        """返回用于诊断的后端消息身份。"""

        ...

    @property
    def possibly_redelivered(self) -> bool:
        """返回消息是否可能是后端恢复的重复投递。"""

        ...

    async def acknowledge(self) -> None:
        """按后端语义确认当前消息已经处理完毕。"""

        ...


class QueueConsumer(Protocol):
    """按后端语义接收消息，并负责释放消费资源。"""

    async def receive(self) -> Delivery:
        """等待并返回下一条尚未确认的消息。"""

        ...

    async def aclose(self) -> None:
        """停止消费并释放订阅或连接资源。"""

        ...
