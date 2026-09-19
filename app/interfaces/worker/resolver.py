"""从启动期任务目录解析并执行 QueueJob。"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Protocol, cast

from pydantic import ValidationError

from app.infrastructure.queue.contracts.codec import JobDecoder
from app.infrastructure.queue.errors import (
    InvalidMessageError,
    JobDecodeError,
    JobDefinitionError,
    QueueConfigurationError,
    UnknownJobError,
    UnsupportedJobVersionError,
)
from app.infrastructure.queue.job import JobDescriptor, QueueJob, describe_job
from app.infrastructure.queue.policies import JobPolicy
from app.interfaces.worker.context import JobExecutionContext


class ExecutableJob(Protocol):
    """JobExecutor 所需的任务策略和 payload 执行能力。"""

    @property
    def policy(self) -> JobPolicy:
        """返回 Worker 重试和超时所需的任务策略。"""

        ...

    async def execute(self, payload: bytes, context: JobExecutionContext) -> None:
        """解码业务 payload，并使用单任务上下文执行具体任务。"""

        ...


class JobTypeResolver(Protocol):
    """按稳定类型引用和版本查找任务，并保留消息错误与部署错误分类。"""

    def resolve(self, reference: str, version: int) -> ExecutableJob:
        """返回绑定；未知引用/版本和任务定义缺陷应抛出对应队列错误。"""

        ...


@dataclass(frozen=True, slots=True)
class JobBinding[T: QueueJob[JobExecutionContext]]:
    """绑定已验证的任务描述，并负责 payload 解码和执行。"""

    descriptor: JobDescriptor[T]
    decoder: JobDecoder[T]

    @property
    def policy(self) -> JobPolicy:
        """返回任务类型声明的不可变执行策略。"""

        return self.descriptor.policy

    async def execute(self, payload: bytes, context: JobExecutionContext) -> None:
        """恢复准确任务类型后把单任务上下文交给 handle。"""

        try:
            job = self.decoder.decode(payload)
        except JobDecodeError:
            raise
        except (InvalidMessageError, ValidationError) as error:
            raise JobDecodeError("业务任务数据解码失败") from error
        except Exception as error:
            # Decoder 必须显式区分坏数据；其他异常表示已部署任务定义有缺陷。
            raise JobDefinitionError("任务 Decoder 执行失败") from error
        if type(job) is not self.descriptor.job_type:
            raise JobDefinitionError("任务 Decoder 返回了错误的任务类型")
        await job.handle(context)


@dataclass(frozen=True, slots=True)
class JobResolver:
    """校验发现结果并从不可变任务目录解析消息引用。"""

    job_types: tuple[type[QueueJob[JobExecutionContext]], ...]
    _descriptors: tuple[JobDescriptor[QueueJob[JobExecutionContext]], ...] = field(init=False, repr=False)
    _bindings: Mapping[tuple[str, int], ExecutableJob] = field(init=False, repr=False)
    _references: frozenset[str] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """在开始消费前校验任务定义、引用唯一性和全部版本绑定。"""

        descriptor_by_reference: dict[str, JobDescriptor[QueueJob[JobExecutionContext]]] = {}
        bindings: dict[tuple[str, int], ExecutableJob] = {}
        descriptors: list[JobDescriptor[QueueJob[JobExecutionContext]]] = []
        for job_type in self.job_types:
            try:
                descriptor = cast(JobDescriptor[QueueJob[JobExecutionContext]], describe_job(job_type))
            except Exception as error:
                raise QueueConfigurationError("发现的队列任务定义不合法") from error

            references = (descriptor.reference, *descriptor.legacy_references)
            for reference in references:
                if reference in descriptor_by_reference:
                    raise QueueConfigurationError(f"队列任务引用 {reference!r} 重复")
                descriptor_by_reference[reference] = descriptor

            for reference in references:
                for version in (descriptor.version, *descriptor.legacy_decoders):
                    bindings[(reference, version)] = JobBinding(descriptor, descriptor.decoder_for(version))
            descriptors.append(descriptor)

        descriptors.sort(key=lambda descriptor: descriptor.reference)
        object.__setattr__(self, "_descriptors", tuple(descriptors))
        object.__setattr__(self, "_bindings", MappingProxyType(bindings))
        object.__setattr__(self, "_references", frozenset(descriptor_by_reference))

    def resolve(self, reference: str, version: int) -> ExecutableJob:
        """查询预校验绑定，并区分未知引用和不兼容版本。"""

        if reference not in self._references:
            raise UnknownJobError("任务引用未发现")
        if type(version) is not int or version < 1:
            raise UnsupportedJobVersionError("任务消息版本不受支持")
        try:
            return self._bindings[(reference, version)]
        except KeyError:
            raise UnsupportedJobVersionError("任务消息版本不受支持") from None

    @property
    def descriptors(self) -> tuple[JobDescriptor[QueueJob[JobExecutionContext]], ...]:
        """返回按稳定引用排序的不可变任务描述快照。"""

        return self._descriptors
