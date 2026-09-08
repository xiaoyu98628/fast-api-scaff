"""根据消息中的类路径动态解析并执行 QueueJob。"""

from dataclasses import dataclass
from functools import cache
from importlib import import_module
from typing import Protocol, cast

from app.infrastructure.queue.errors import InvalidMessageError, QueueConfigurationError
from app.infrastructure.queue.job import JobDescriptor, QueueJob, describe_job
from app.infrastructure.queue.policies import JobPolicy


class ExecutableJob(Protocol):
    """JobExecutor 所需的任务策略和 payload 执行能力。"""

    @property
    def policy(self) -> JobPolicy:
        """返回 Worker 重试和超时所需的任务策略。"""

        ...

    async def execute(self, payload: bytes) -> None:
        """解码业务 payload 并执行具体任务。"""

        ...


class JobTypeResolver(Protocol):
    """按稳定类型引用和版本查找可执行任务。"""

    def resolve(self, reference: str, version: int) -> ExecutableJob:
        """解析匹配类型引用和版本的可执行任务绑定。"""

        ...


@dataclass(frozen=True, slots=True)
class JobBinding[T: QueueJob]:
    """绑定已验证的任务描述，并负责 payload 解码和执行。"""

    descriptor: JobDescriptor[T]

    @property
    def policy(self) -> JobPolicy:
        """返回任务类型声明的不可变执行策略。"""

        return self.descriptor.policy

    async def execute(self, payload: bytes) -> None:
        """恢复准确任务类型后调用其无参数 handle。"""

        try:
            job = self.descriptor.codec.decode(payload)
            if type(job) is not self.descriptor.job_type:
                raise TypeError("Codec 返回了错误的任务类型")
        except Exception as error:
            raise InvalidMessageError("业务任务数据解码失败") from error
        await job.handle()


@dataclass(frozen=True)
class JobResolver:
    """只允许从可信应用包动态导入模块级 QueueJob 类型。"""

    allowed_packages: tuple[str, ...] = ("app",)

    def __post_init__(self) -> None:
        """确保动态导入白名单至少包含一个有效包名。"""

        if not self.allowed_packages or any(not package.strip() for package in self.allowed_packages):
            raise QueueConfigurationError("任务模块范围不合法")

    @cache
    def resolve(self, reference: str, version: int) -> ExecutableJob:
        """解析并缓存任务绑定；未知类型和版本统一表现为 KeyError。"""

        try:
            job_type = self._load(reference)
            descriptor = describe_job(job_type)
        except Exception:
            raise KeyError((reference, version)) from None
        if descriptor.version != version:
            raise KeyError((reference, version))
        return JobBinding(descriptor)

    def _load(self, reference: str) -> type[QueueJob]:
        """从白名单模块加载模块级 QueueJob 子类。"""

        # 类路径来自队列消息，因此导入前必须先限制在可信包前缀内。
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
