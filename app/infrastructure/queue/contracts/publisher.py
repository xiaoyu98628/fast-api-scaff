"""定义 Dispatcher 依赖的最小消息发布契约。"""

from typing import Protocol


class QueuePublisher(Protocol):
    """向指定逻辑队列发布已经编码的信封字节。"""

    async def publish(self, queue: str, payload: bytes) -> None:
        """把完整信封字节提交给当前队列连接。"""

        ...
