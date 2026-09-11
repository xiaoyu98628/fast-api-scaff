"""在一次性 Console 进程中托管应用运行时。"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from uuid import UUID, uuid4

from app.bootstrap.build import build_application_container
from app.config.settings import Settings
from app.infrastructure.logging.context import bind_console_log_context, current_console_command_id
from app.interfaces.console.context import ConsoleContext
from app.interfaces.console.contracts import ConsoleOperation
from app.interfaces.console.presentation import ConsolePresenter
from app.runtime.container import ApplicationContainer
from app.runtime.lifecycle import ApplicationRuntime

type ContainerBuilder = Callable[[Settings], ApplicationContainer]
type CommandIdFactory = Callable[[], UUID]


@dataclass(frozen=True, slots=True)
class ConsoleHost:
    """在一次性进程中执行依赖应用容器的操作。"""

    settings: Settings
    container_builder: ContainerBuilder = build_application_container
    presenter: ConsolePresenter = field(default_factory=ConsolePresenter)
    command_id_factory: CommandIdFactory = uuid4

    def run[T](self, operation: ConsoleOperation[T]) -> T:
        """从同步 CLI 回调进入异步应用运行时。"""

        command_id = current_console_command_id()
        if command_id is not None:
            return asyncio.run(self._run(operation, command_id))

        command_id = str(self.command_id_factory())
        with bind_console_log_context(command_id):
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
