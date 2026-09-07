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

type ContainerBuilder = Callable[[Settings], ApplicationContainer]


@dataclass(frozen=True, slots=True)
class ConsoleHost:
    """在一次性进程中执行依赖应用容器的操作。"""

    settings: Settings
    container_builder: ContainerBuilder = build_application_container
    presenter: ConsolePresenter = field(default_factory=ConsolePresenter)

    def run[T](self, operation: ConsoleOperation[T]) -> T:
        return asyncio.run(self._run(operation))

    async def _run[T](self, operation: ConsoleOperation[T]) -> T:
        runtime = ApplicationRuntime(partial(self.container_builder, self.settings))

        async with runtime as container:
            return await operation(ConsoleContext(settings=self.settings, container=container))
