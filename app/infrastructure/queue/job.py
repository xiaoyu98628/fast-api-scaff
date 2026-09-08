from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import cache
from typing import Any, ClassVar, cast

from app.infrastructure.queue.codecs.job_json import JsonJobCodec
from app.infrastructure.queue.contracts.codec import JobCodec
from app.infrastructure.queue.errors import QueueConfigurationError
from app.infrastructure.queue.policies import JobPolicy


class QueueJob(ABC):
    version: ClassVar[int] = 1
    policy: ClassVar[JobPolicy] = JobPolicy()
    codec: ClassVar[JobCodec[Any] | None] = None

    @abstractmethod
    async def handle(self) -> None:
        pass


@dataclass(frozen=True, slots=True)
class EncodedJob:
    job_type: str
    version: int
    payload: bytes


@dataclass(frozen=True, slots=True)
class JobDescriptor[T: QueueJob]:
    reference: str
    version: int
    job_type: type[T]
    codec: JobCodec[T]
    policy: JobPolicy

    def encode(self, job: object) -> EncodedJob:
        if type(job) is not self.job_type:
            raise TypeError("任务类型与描述类型不一致")
        return EncodedJob(self.reference, self.version, self.codec.encode(cast(T, job)))


def job_reference(job_type: type[QueueJob]) -> str:
    module = job_type.__module__.strip()
    qualified_name = job_type.__qualname__.strip()
    if not module or not qualified_name or "<locals>" in qualified_name:
        raise QueueConfigurationError("队列任务必须是可导入的模块级类")
    reference = f"{module}:{qualified_name}"
    if len(reference) > 500:
        raise QueueConfigurationError("队列任务类路径过长")
    return reference


@cache
def describe_job[T: QueueJob](job_type: type[T]) -> JobDescriptor[T]:
    if not issubclass(job_type, QueueJob):
        raise QueueConfigurationError("任务类型必须继承 QueueJob")
    version = job_type.version
    if type(version) is not int or version < 1:
        raise QueueConfigurationError("任务版本不合法")
    policy = job_type.policy
    if not isinstance(policy, JobPolicy):
        raise QueueConfigurationError("任务策略不合法")
    configured_codec = job_type.codec
    codec = JsonJobCodec(job_type) if configured_codec is None else cast(JobCodec[T], configured_codec)
    return JobDescriptor(job_reference(job_type), version, job_type, codec, policy)


def encode_job(job: object) -> EncodedJob:
    if not isinstance(job, QueueJob):
        raise QueueConfigurationError("任务必须继承 QueueJob")
    return describe_job(type(job)).encode(job)
