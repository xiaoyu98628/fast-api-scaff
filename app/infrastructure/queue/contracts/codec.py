"""定义业务任务 payload 的驱动无关编解码契约。"""

from typing import Protocol


class JobCodec[T](Protocol):
    """在具体 QueueJob 与其消息 payload 字节之间转换。"""

    def encode(self, job: T) -> bytes: ...
    def decode(self, payload: bytes) -> T: ...
