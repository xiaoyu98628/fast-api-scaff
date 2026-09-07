from dataclasses import dataclass
from typing import Protocol, cast

from app.infrastructure.queue.contracts.codec import JobCodec
from app.infrastructure.queue.errors import QueueConfigurationError


@dataclass(frozen=True, slots=True)
class EncodedJob:
    name: str
    version: int
    payload: bytes


class JobEncoder(Protocol):
    def encode(self, job: object) -> EncodedJob: ...


@dataclass(frozen=True, slots=True)
class JobDefinition[T]:
    name: str
    version: int
    job_type: type[T]
    codec: JobCodec[T]

    def __post_init__(self) -> None:
        if not self.name.strip() or type(self.version) is not int or self.version < 1:
            raise QueueConfigurationError("任务名称或版本不合法")

    def encode(self, job: object) -> EncodedJob:
        if type(job) is not self.job_type:
            raise TypeError("任务类型与注册类型不一致")
        return EncodedJob(self.name, self.version, self.codec.encode(cast(T, job)))


class JobCatalog:
    def __init__(self) -> None:
        self._encoders: dict[type, JobEncoder] = {}
        self._keys: set[tuple[str, int]] = set()

    def register[T](self, definition: JobDefinition[T]) -> None:
        key = (definition.name, definition.version)
        if key in self._keys or definition.job_type in self._encoders:
            raise QueueConfigurationError("任务重复注册")
        self._keys.add(key)
        self._encoders[definition.job_type] = definition

    def encode(self, job: object) -> EncodedJob:
        try:
            encoder = self._encoders[type(job)]
        except KeyError:
            raise QueueConfigurationError("任务类型尚未注册") from None
        return encoder.encode(job)
