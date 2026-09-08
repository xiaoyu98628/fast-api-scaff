from dataclasses import dataclass
from functools import cache
from importlib import import_module
from typing import Protocol, cast

from app.infrastructure.queue.errors import InvalidMessageError, QueueConfigurationError
from app.infrastructure.queue.job import JobDescriptor, QueueJob, describe_job
from app.infrastructure.queue.policies import JobPolicy


class ExecutableJob(Protocol):
    @property
    def policy(self) -> JobPolicy: ...
    async def execute(self, payload: bytes) -> None: ...


class JobTypeResolver(Protocol):
    def resolve(self, reference: str, version: int) -> ExecutableJob: ...


@dataclass(frozen=True, slots=True)
class JobBinding[T: QueueJob]:
    descriptor: JobDescriptor[T]

    @property
    def policy(self) -> JobPolicy:
        return self.descriptor.policy

    async def execute(self, payload: bytes) -> None:
        try:
            job = self.descriptor.codec.decode(payload)
            if type(job) is not self.descriptor.job_type:
                raise TypeError("Codec 返回了错误的任务类型")
        except Exception as error:
            raise InvalidMessageError("业务任务数据解码失败") from error
        await job.handle()


@dataclass(frozen=True)
class JobResolver:
    allowed_packages: tuple[str, ...] = ("app",)

    def __post_init__(self) -> None:
        if not self.allowed_packages or any(not package.strip() for package in self.allowed_packages):
            raise QueueConfigurationError("任务模块范围不合法")

    @cache
    def resolve(self, reference: str, version: int) -> ExecutableJob:
        try:
            job_type = self._load(reference)
            descriptor = describe_job(job_type)
        except Exception:
            raise KeyError((reference, version)) from None
        if descriptor.version != version:
            raise KeyError((reference, version))
        return JobBinding(descriptor)

    def _load(self, reference: str) -> type[QueueJob]:
        module_name, separator, qualified_name = reference.partition(":")
        if not separator or not module_name or not qualified_name or "<locals>" in qualified_name:
            raise ValueError("任务类路径不合法")
        if not any(module_name == package or module_name.startswith(f"{package}.") for package in self.allowed_packages):
            raise ValueError("任务模块不在允许范围内")
        value: object = import_module(module_name)
        for part in qualified_name.split("."):
            value = getattr(value, part)
        if not isinstance(value, type) or not issubclass(value, QueueJob):
            raise TypeError("任务类必须继承 QueueJob")
        return cast(type[QueueJob], value)
