"""实现 QueueJob 默认使用的 JSON payload 编解码器。"""

from pydantic import TypeAdapter


class JsonJobCodec[T]:
    """使用任务类型的 Pydantic schema 完成 JSON 编解码。"""

    def __init__(self, job_type: type[T]) -> None:
        """为指定任务类型创建可复用的 Pydantic 适配器。"""

        self._adapter = TypeAdapter(job_type)

    def encode(self, job: T) -> bytes:
        """按照具体 Job 类型的 schema 序列化字段。"""

        return self._adapter.dump_json(job)

    def decode(self, payload: bytes) -> T:
        """校验 payload 并恢复为具体 Job 实例。"""

        return self._adapter.validate_json(payload)
