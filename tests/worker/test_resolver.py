"""验证 Worker 启动期任务目录的引用、版本和执行绑定。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, cast

import pytest

from app.contexts.user.jobs.login_succeeded import LoginSucceededJob
from app.infrastructure.queue.errors import (
    JobDecodeError,
    JobDefinitionError,
    QueueConfigurationError,
    UnknownJobError,
    UnsupportedJobVersionError,
)
from app.infrastructure.queue.job import QueueJob, encode_job, job_type_path
from app.interfaces.worker.context import JobExecutionContext
from app.interfaces.worker.resolver import JobBinding, JobResolver

_HANDLED_VALUES: list[int] = []


class LegacyDecoder:
    """把版本 1 的纯数字 payload 迁移为当前任务对象。"""

    def decode(self, payload: bytes) -> VersionedJob:
        """把旧字段恢复为当前任务并补充新字段默认语义。"""

        try:
            return VersionedJob(value=int(payload) + 100)
        except ValueError as error:
            raise JobDecodeError("版本 1 测试 payload 不合法") from error


@dataclass(frozen=True, slots=True)
class VersionedJob(QueueJob[JobExecutionContext]):
    """提供当前版本和显式历史 Decoder 的测试任务。"""

    value: int
    version: ClassVar[int] = 2
    legacy_decoders: ClassVar = {1: LegacyDecoder()}

    async def handle(self, context: JobExecutionContext) -> None:
        del context
        _HANDLED_VALUES.append(self.value)


class BrokenLegacyDecoder:
    """模拟违反 Decoder 错误契约的部署缺陷。"""

    def decode(self, payload: bytes) -> VersionedJob:
        """抛出未按契约分类的实现异常。"""

        del payload
        raise RuntimeError("decoder bug")


@dataclass(frozen=True, slots=True)
class BrokenVersionedJob(QueueJob[JobExecutionContext]):
    """绑定存在实现缺陷的历史 Decoder。"""

    value: int
    version: ClassVar[int] = 2
    legacy_decoders: ClassVar = {1: BrokenLegacyDecoder()}

    async def handle(self, context: JobExecutionContext) -> None:
        del context


@dataclass(frozen=True, slots=True)
class StableReferenceJob(QueueJob[JobExecutionContext]):
    """使用与 Python 导入路径解耦的稳定任务引用。"""

    value: int
    reference: ClassVar[str | None] = "tests.stable-job"
    legacy_references: ClassVar[tuple[str, ...]] = ("tests.old:StableReferenceJob",)

    async def handle(self, context: JobExecutionContext) -> None:
        del context


@dataclass(frozen=True, slots=True)
class DuplicateReferenceJob(QueueJob[JobExecutionContext]):
    """提供重复引用冲突的测试任务。"""

    reference: ClassVar[str | None] = "tests.stable-job"

    async def handle(self, context: JobExecutionContext) -> None:
        del context


@dataclass(frozen=True, slots=True)
class InvalidReferenceJob(QueueJob[JobExecutionContext]):
    """提供非法稳定引用的测试任务。"""

    reference: ClassVar[str | None] = "tests invalid reference"

    async def handle(self, context: JobExecutionContext) -> None:
        del context


@dataclass(frozen=True, slots=True)
class RepeatedLegacyReferenceJob(QueueJob[JobExecutionContext]):
    """提供与当前引用重复的历史引用。"""

    reference: ClassVar[str | None] = "tests.current"
    legacy_references: ClassVar[tuple[str, ...]] = ("tests.current",)

    async def handle(self, context: JobExecutionContext) -> None:
        del context


def test_resolver_builds_immutable_catalog_and_reuses_binding() -> None:
    encoded = encode_job(LoginSucceededJob())
    resolver = JobResolver((LoginSucceededJob,))

    binding = resolver.resolve(encoded.job_type, encoded.version)

    assert binding is resolver.resolve(encoded.job_type, encoded.version)
    assert binding.policy == LoginSucceededJob.policy
    assert tuple(descriptor.job_type for descriptor in resolver.descriptors) == (LoginSucceededJob,)


def test_resolver_rejects_unknown_reference_and_version() -> None:
    encoded = encode_job(LoginSucceededJob())
    resolver = JobResolver((LoginSucceededJob,))

    with pytest.raises(UnsupportedJobVersionError):
        resolver.resolve(encoded.job_type, encoded.version + 1)
    with pytest.raises(UnsupportedJobVersionError):
        resolver.resolve(encoded.job_type, 0)
    with pytest.raises(UnknownJobError):
        resolver.resolve("tests.queue.fakes:Job", 1)


@pytest.mark.asyncio
async def test_resolver_executes_supported_legacy_version_with_current_job_type() -> None:
    _HANDLED_VALUES.clear()
    resolver = JobResolver((VersionedJob,))
    binding = resolver.resolve(job_type_path(VersionedJob), 1)

    await binding.execute(b"7", cast(JobExecutionContext, object()))

    assert _HANDLED_VALUES == [107]


@pytest.mark.asyncio
async def test_resolver_exposes_unexpected_decoder_failure_as_definition_error() -> None:
    resolver = JobResolver((BrokenVersionedJob,))
    binding = resolver.resolve(job_type_path(BrokenVersionedJob), 1)

    with pytest.raises(JobDefinitionError, match="Decoder 执行失败"):
        await binding.execute(b"7", cast(JobExecutionContext, object()))


def test_resolver_accepts_current_and_legacy_stable_references() -> None:
    resolver = JobResolver((StableReferenceJob,))
    encoded = encode_job(StableReferenceJob(7))
    current_binding = cast(JobBinding[StableReferenceJob], resolver.resolve(encoded.job_type, encoded.version))
    legacy_binding = cast(JobBinding[StableReferenceJob], resolver.resolve("tests.old:StableReferenceJob", 1))

    assert encoded.job_type == "tests.stable-job"
    assert current_binding.descriptor.job_type is StableReferenceJob
    assert legacy_binding.descriptor.job_type is StableReferenceJob
    assert resolver.descriptors[0].legacy_references == ("tests.old:StableReferenceJob",)
    assert job_type_path(StableReferenceJob) == "tests.worker.test_resolver:StableReferenceJob"


def test_resolver_rejects_duplicate_references_before_consuming() -> None:
    with pytest.raises(QueueConfigurationError, match="引用 .* 重复"):
        JobResolver((StableReferenceJob, DuplicateReferenceJob))


def test_resolver_rejects_abstract_job_before_consuming() -> None:
    abstract_job = cast(type[QueueJob[JobExecutionContext]], QueueJob)

    with pytest.raises(QueueConfigurationError, match="发现的队列任务定义不合法"):
        JobResolver((abstract_job,))


@pytest.mark.parametrize("job_type", [InvalidReferenceJob, RepeatedLegacyReferenceJob])
def test_resolver_rejects_invalid_reference_contract_before_consuming(
    job_type: type[QueueJob[JobExecutionContext]],
) -> None:
    with pytest.raises(QueueConfigurationError, match="发现的队列任务定义不合法"):
        JobResolver((job_type,))
