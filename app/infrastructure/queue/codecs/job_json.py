from pydantic import TypeAdapter


class JsonJobCodec[T]:
    """使用任务类型的 Pydantic schema 完成 JSON 编解码。"""

    def __init__(self, job_type: type[T]) -> None:
        self._adapter = TypeAdapter(job_type)

    def encode(self, job: T) -> bytes:
        return self._adapter.dump_json(job)

    def decode(self, payload: bytes) -> T:
        return self._adapter.validate_json(payload)
