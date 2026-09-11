"""在一次性 Console 进程中托管应用运行时。"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial

from app.bootstrap.build import build_application_container
from app.config.settings import Settings
from app.interfaces.console.context import ConsoleContext
from app.interfaces.console.contracts import ConsoleOperation
from app.interfaces.console.presentation import ConsolePresenter
from app.runtime.container import ApplicationContainer
from app.runtime.lifecycle import ApplicationRuntime
from app.runtime.trace import TraceContext, TraceIdFactory, bind_trace_context, current_trace_context, new_trace_id

type ContainerBuilder = Callable[[Settings], ApplicationContainer]


@dataclass(frozen=True, slots=True)
class ConsoleHost:
    """在一次性进程中执行依赖应用容器的操作。"""

    settings: Settings
    container_builder: ContainerBuilder = build_application_container
    presenter: ConsolePresenter = field(default_factory=ConsolePresenter)
    command_id_factory: TraceIdFactory = new_trace_id

    def run[T](self, operation: ConsoleOperation[T]) -> T:
        """从同步 CLI 回调进入异步应用运行时。"""

        trace_context = current_trace_context()
        command_id = trace_context.command_id if trace_context is not None else None
        if command_id is not None:
            return asyncio.run(self._run(operation, command_id))

        command_id = self.command_id_factory()
        trace_context = TraceContext(correlation_id=command_id, command_id=command_id)
        with bind_trace_context(trace_context):
            return asyncio.run(self._run(operation, command_id))

    async def _run[T](self, operation: ConsoleOperation[T], command_id: str) -> T:
        """在容器生命周期内执行一次 Console 操作。"""

        runtime = ApplicationRuntime(partial(self.container_builder, self.settings))

        # 即使命令失败，异步上下文管理器也会关闭本次命令使用的全部资源。
        async with runtime as container:
            return await operation(
                ConsoleContext(
                    settings=self.settings,
                    container=container,
                    command_id=command_id,
                )
            )
