"""验证 Worker 对任务类型、版本和导入白名单的解析。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, cast
from unittest.mock import Mock

import pytest

import app.interfaces.worker.resolver as resolver_module
from app.contexts.user.jobs.login_succeeded import LoginSucceededJob
from app.infrastructure.queue.errors import (
    JobDecodeError,
    JobDefinitionError,
    QueueConfigurationError,
    UnknownJobError,
    UnsupportedJobVersionError,
)
from app.infrastructure.queue.job import QueueJob, encode_job
from app.interfaces.worker.context import JobExecutionContext
from app.interfaces.worker.resolver import JobResolver

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


def test_resolver_dynamically_loads_and_caches_queue_job() -> None:
    encoded = encode_job(LoginSucceededJob())
    resolver = JobResolver()

    binding = resolver.resolve(encoded.job_type, encoded.version)

    assert binding is resolver.resolve(encoded.job_type, encoded.version)
    assert binding.policy == LoginSucceededJob.policy


def test_resolver_rejects_unknown_version_and_external_module() -> None:
    encoded = encode_job(LoginSucceededJob())
    resolver = JobResolver()

    with pytest.raises(UnsupportedJobVersionError):
        resolver.resolve(encoded.job_type, encoded.version + 1)
    with pytest.raises(UnknownJobError):
        resolver.resolve("tests.queue.fakes:Job", 1)


@pytest.mark.asyncio
async def test_resolver_executes_supported_legacy_version_with_current_job_type() -> None:
    _HANDLED_VALUES.clear()
    resolver = JobResolver(("tests",))
    binding = resolver.resolve("tests.worker.test_resolver:VersionedJob", 1)

    await binding.execute(b"7", cast(JobExecutionContext, object()))

    assert _HANDLED_VALUES == [107]


@pytest.mark.asyncio
async def test_resolver_exposes_unexpected_decoder_failure_as_definition_error() -> None:
    resolver = JobResolver(("tests",))
    binding = resolver.resolve("tests.worker.test_resolver:BrokenVersionedJob", 1)

    with pytest.raises(JobDefinitionError, match="Decoder 执行失败"):
        await binding.execute(b"7", cast(JobExecutionContext, object()))


def test_resolver_does_not_mask_job_module_dependency_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    missing_dependency = ModuleNotFoundError("No module named 'missing_dependency'", name="missing_dependency")
    monkeypatch.setattr(resolver_module, "import_module", Mock(side_effect=missing_dependency))

    with pytest.raises(JobDefinitionError, match="依赖导入失败"):
        JobResolver().resolve("app.contexts.user.jobs.example:ExampleJob", 1)


@pytest.mark.parametrize("allowed_packages", [(), ("",)])
def test_resolver_rejects_invalid_allowed_packages(allowed_packages: tuple[str, ...]) -> None:
    with pytest.raises(QueueConfigurationError):
        JobResolver(allowed_packages)
