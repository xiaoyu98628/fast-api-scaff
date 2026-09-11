"""定义可投递 QueueJob 及其类型描述和编码规则。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import cache
from typing import Any, ClassVar, cast

from app.infrastructure.queue.codecs.job_json import JsonJobCodec
from app.infrastructure.queue.contracts.codec import JobCodec
from app.infrastructure.queue.errors import QueueConfigurationError
from app.infrastructure.queue.policies import JobPolicy


class QueueJob[TContext](ABC):
    """把可序列化任务数据与单次执行上下文入口收敛在同一类型。"""

    version: ClassVar[int] = 1
    policy: ClassVar[JobPolicy] = JobPolicy()
    codec: ClassVar[JobCodec[Any] | None] = None

    @abstractmethod
    async def handle(self, context: TContext) -> None:
        """使用单次执行上下文处理已经从消息 payload 恢复的任务。"""

        pass


@dataclass(frozen=True, slots=True)
class EncodedJob:
    """投递前生成的任务类型、版本和业务 payload。"""

    job_type: str
    version: int
    payload: bytes


@dataclass(frozen=True, slots=True)
class JobDescriptor[T: QueueJob[Any]]:
    """缓存一个 QueueJob 类型的稳定消息契约。"""

    reference: str
    version: int
    job_type: type[T]
    codec: JobCodec[T]
    policy: JobPolicy

    def encode(self, job: object) -> EncodedJob:
        """防止调用方用其他子类实例绕过当前描述。"""

        if type(job) is not self.job_type:
            raise TypeError("任务类型与描述类型不一致")
        return EncodedJob(self.reference, self.version, self.codec.encode(cast(T, job)))


def job_reference(job_type: type[QueueJob[Any]]) -> str:
    """生成 Worker 可动态导入的 ``module:qualname`` 类型标识。"""

    module = job_type.__module__.strip()
    qualified_name = job_type.__qualname__.strip()
    if not module or not qualified_name or "<locals>" in qualified_name:
        raise QueueConfigurationError("队列任务必须是可导入的模块级类")
    reference = f"{module}:{qualified_name}"
    if len(reference) > 500:
        raise QueueConfigurationError("队列任务类路径过长")
    return reference


@cache
def describe_job[T: QueueJob[Any]](job_type: type[T]) -> JobDescriptor[T]:
    """验证并缓存任务类型配置，未声明 Codec 时使用 JSON。"""

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
    """验证 QueueJob 实例并按照其具体类型完成编码。"""

    if not isinstance(job, QueueJob):
        raise QueueConfigurationError("任务必须继承 QueueJob")
    return describe_job(type(job)).encode(job)
