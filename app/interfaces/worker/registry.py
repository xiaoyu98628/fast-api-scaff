from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from app.infrastructure.queue.catalog import JobDefinition
from app.infrastructure.queue.contracts.codec import JobCodec
from app.infrastructure.queue.errors import InvalidMessageError, QueueConfigurationError
from app.infrastructure.queue.policies import JobPolicy


class ExecutableJob(Protocol):
    @property
    def policy(self) -> JobPolicy: ...
    async def execute(self, payload: bytes) -> None: ...


@dataclass(frozen=True, slots=True)
class HandlerBinding[T]:
    codec: JobCodec[T]
    handler: Callable[[T], Awaitable[None]]
    policy: JobPolicy

    async def execute(self, payload: bytes) -> None:
        try:
            job = self.codec.decode(payload)
        except Exception as error:
            raise InvalidMessageError("业务任务数据解码失败") from error
        await self.handler(job)


class HandlerRegistry:
    def __init__(self) -> None:
        self._bindings: dict[tuple[str, int], ExecutableJob] = {}

    def register[T](self, definition: JobDefinition[T], handler: Callable[[T], Awaitable[None]], *, policy: JobPolicy = JobPolicy()) -> None:
        key = (definition.name, definition.version)
        if key in self._bindings:
            raise QueueConfigurationError("Handler 重复注册")
        self._bindings[key] = HandlerBinding(definition.codec, handler, policy)

    def resolve(self, name: str, version: int) -> ExecutableJob:
        return self._bindings[(name, version)]

    def require_handlers(self) -> None:
        if not self._bindings:
            raise QueueConfigurationError("尚未注册 Worker Handler，请在 worker/composition.py 显式装配")
