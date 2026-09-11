"""定义业务任务 payload 的驱动无关编解码契约。"""

from typing import Protocol


class JobCodec[T](Protocol):
    """在具体 QueueJob 与其消息 payload 字节之间转换。"""

    def encode(self, job: T) -> bytes:
        """把具体任务实例编码为驱动无关的 payload 字节。"""

        ...

    def decode(self, payload: bytes) -> T:
        """校验 payload 并恢复具体任务实例。"""

        ...


class JobDecoder[T](Protocol):
    """把指定历史版本的 payload 恢复或迁移为当前 QueueJob。"""

    def decode(self, payload: bytes) -> T:
        """返回当前 Job 类型；数据错误应抛出 JobDecodeError。"""

        ...
