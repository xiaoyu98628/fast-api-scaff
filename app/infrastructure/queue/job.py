"""定义可投递 QueueJob 及其类型描述和编码规则。"""

import re
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from inspect import isabstract
from types import MappingProxyType
from typing import Any, ClassVar, cast

from app.infrastructure.queue.codecs.job_json import JsonJobCodec
from app.infrastructure.queue.contracts.codec import JobCodec, JobDecoder
from app.infrastructure.queue.errors import QueueConfigurationError, UnsupportedJobVersionError
from app.infrastructure.queue.policies import JobPolicy

_JOB_REFERENCE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,499}")


class QueueJob[TContext](ABC):
    """把可序列化任务数据与单次执行上下文入口收敛在同一类型。"""

    reference: ClassVar[str | None] = None
    legacy_references: ClassVar[tuple[str, ...]] = ()
    version: ClassVar[int] = 1
    policy: ClassVar[JobPolicy] = JobPolicy()
    codec: ClassVar[JobCodec[Any] | None] = None
    legacy_decoders: ClassVar[Mapping[int, JobDecoder[Any]]] = MappingProxyType({})

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
    legacy_references: tuple[str, ...]
    version: int
    job_type: type[T]
    codec: JobCodec[T]
    legacy_decoders: Mapping[int, JobDecoder[T]]
    policy: JobPolicy

    def encode(self, job: object) -> EncodedJob:
        """防止调用方用其他子类实例绕过当前描述。"""

        if type(job) is not self.job_type:
            raise TypeError("任务类型与描述类型不一致")
        return EncodedJob(self.reference, self.version, self.codec.encode(cast(T, job)))

    def decoder_for(self, version: int) -> JobDecoder[T]:
        """返回消息版本对应的 Decoder，不支持时保留独立错误分类。"""

        if type(version) is not int or version < 1:
            raise UnsupportedJobVersionError("任务消息版本不受支持")
        if version == self.version:
            return self.codec
        try:
            return self.legacy_decoders[version]
        except KeyError:
            raise UnsupportedJobVersionError("任务消息版本不受支持") from None


def job_reference(job_type: type[QueueJob[Any]]) -> str:
    """返回显式稳定引用，未声明时回退到模块级类路径。"""

    default_reference = job_type_path(job_type)
    configured_reference = job_type.reference
    if configured_reference is None:
        return default_reference
    return _validate_job_reference(configured_reference, label="任务稳定引用")


def job_type_path(job_type: type[QueueJob[Any]]) -> str:
    """返回可用于诊断的模块级 ``module:qualname`` 类路径。"""

    module = job_type.__module__.strip()
    qualified_name = job_type.__qualname__.strip()
    if not module or not qualified_name or "<locals>" in qualified_name:
        raise QueueConfigurationError("队列任务必须是可导入的模块级类")
    return _validate_job_reference(f"{module}:{qualified_name}", label="任务类路径")


@cache
def describe_job[T: QueueJob[Any]](job_type: type[T]) -> JobDescriptor[T]:
    """验证并缓存任务类型、当前 Codec 和历史版本 Decoder。"""

    if not isinstance(job_type, type) or not issubclass(job_type, QueueJob):
        raise QueueConfigurationError("任务类型必须继承 QueueJob")
    if isabstract(job_type):
        raise QueueConfigurationError("任务类型不能是抽象类")
    reference = job_reference(job_type)
    legacy_references = _validate_legacy_references(job_type, reference)
    version = job_type.version
    if type(version) is not int or version < 1:
        raise QueueConfigurationError("任务版本不合法")
    policy = job_type.policy
    if not isinstance(policy, JobPolicy):
        raise QueueConfigurationError("任务策略不合法")
    configured_codec = job_type.codec
    codec = JsonJobCodec(job_type) if configured_codec is None else cast(JobCodec[T], configured_codec)
    if not callable(getattr(codec, "encode", None)) or not callable(getattr(codec, "decode", None)):
        raise QueueConfigurationError("任务 Codec 不合法")

    configured_decoders = job_type.legacy_decoders
    if not isinstance(configured_decoders, Mapping):
        raise QueueConfigurationError("任务历史 Decoder 配置不合法")
    legacy_decoders: dict[int, JobDecoder[T]] = {}
    for legacy_version, decoder in configured_decoders.items():
        if type(legacy_version) is not int or not 1 <= legacy_version < version:
            raise QueueConfigurationError("任务历史版本必须是小于当前版本的正整数")
        if not callable(getattr(decoder, "decode", None)):
            raise QueueConfigurationError("任务历史 Decoder 不合法")
        legacy_decoders[legacy_version] = cast(JobDecoder[T], decoder)

    return JobDescriptor(
        reference,
        legacy_references,
        version,
        job_type,
        codec,
        MappingProxyType(legacy_decoders),
        policy,
    )


def encode_job(job: object) -> EncodedJob:
    """验证 QueueJob 实例并按照其具体类型完成编码。"""

    if not isinstance(job, QueueJob):
        raise QueueConfigurationError("任务必须继承 QueueJob")
    return describe_job(type(job)).encode(job)


def _validate_job_reference(value: object, *, label: str) -> str:
    """校验消息协议中的任务引用为短小、可移植的 ASCII 标识。"""

    if not isinstance(value, str) or _JOB_REFERENCE_PATTERN.fullmatch(value) is None:
        raise QueueConfigurationError(f"{label}不合法")
    return value


def _validate_legacy_references(job_type: type[QueueJob[Any]], reference: str) -> tuple[str, ...]:
    """验证移动或重命名任务时保留的历史引用。"""

    configured = job_type.legacy_references
    if not isinstance(configured, tuple):
        raise QueueConfigurationError("任务历史引用必须是元组")
    legacy_references = tuple(_validate_job_reference(item, label="任务历史引用") for item in configured)
    if reference in legacy_references or len(set(legacy_references)) != len(legacy_references):
        raise QueueConfigurationError("任务历史引用不能与当前引用或彼此重复")
    return legacy_references
