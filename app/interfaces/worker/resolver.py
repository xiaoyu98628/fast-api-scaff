"""根据消息中的类路径动态解析并执行 QueueJob。"""

from dataclasses import dataclass
from functools import cache
from importlib import import_module
from typing import Protocol, cast

from pydantic import ValidationError

from app.infrastructure.queue.contracts.codec import JobDecoder
from app.infrastructure.queue.errors import (
    InvalidMessageError,
    JobDecodeError,
    JobDefinitionError,
    QueueConfigurationError,
    UnknownJobError,
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
        """解析并缓存任务绑定，同时区分未知消息和部署定义错误。"""

        try:
            job_type = self._load(reference)
            descriptor = describe_job(job_type)
        except UnknownJobError:
            raise
        except QueueConfigurationError as error:
            raise JobDefinitionError("队列任务定义不合法") from error
        return JobBinding(descriptor, descriptor.decoder_for(version))

    def _load(self, reference: str) -> type[QueueJob[JobExecutionContext]]:
        """从白名单模块加载模块级 QueueJob 子类。"""

        # 类路径来自队列消息，因此导入前必须先限制在可信包前缀内。
        module_name, separator, qualified_name = reference.partition(":")
        if not separator or not module_name or not qualified_name or "<locals>" in qualified_name:
            raise UnknownJobError("任务类路径不合法")
        if not any(module_name == package or module_name.startswith(f"{package}.") for package in self.allowed_packages):
            raise UnknownJobError("任务模块不在允许范围内")
        try:
            value: object = import_module(module_name)
        except ModuleNotFoundError as error:
            if error.name is not None and (module_name == error.name or module_name.startswith(f"{error.name}.")):
                raise UnknownJobError("任务模块不存在") from None
            raise JobDefinitionError("任务模块依赖导入失败") from error
        except Exception as error:
            raise JobDefinitionError("任务模块导入失败") from error
        for part in qualified_name.split("."):
            try:
                value = getattr(value, part)
            except AttributeError:
                raise UnknownJobError("任务类型不存在") from None
            except Exception as error:
                raise JobDefinitionError("任务类型读取失败") from error
        if not isinstance(value, type) or not issubclass(value, QueueJob):
            raise UnknownJobError("任务类型必须继承 QueueJob")
        return cast(type[QueueJob[JobExecutionContext]], value)
