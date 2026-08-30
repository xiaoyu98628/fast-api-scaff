import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import partial

from app.bootstrap.build import build_application_container
from app.bootstrap.container import ApplicationContainer
from app.bootstrap.runtime import ApplicationRuntime
from app.config.settings import Settings, load_settings
from app.infrastructure.logging.configure import configure_logging
from app.interfaces.console.context import ConsoleContext

type SettingsLoader = Callable[[], Settings]
type ContainerBuilder = Callable[[Settings], ApplicationContainer]
type ConsoleOperation[T] = Callable[[ConsoleContext], Awaitable[T]]


@dataclass(frozen=True, slots=True)
class ConsoleApplication:
    """在一次性进程中执行依赖应用容器的操作。"""

    settings_loader: SettingsLoader = load_settings
    container_builder: ContainerBuilder = build_application_container

    def run[T](self, operation: ConsoleOperation[T]) -> T:
        settings = self.settings_loader()
        configure_logging(settings)
        return asyncio.run(self._run(settings, operation))

    async def _run[T](self, settings: Settings, operation: ConsoleOperation[T]) -> T:
        runtime = ApplicationRuntime(partial(self.container_builder, settings))

        async with runtime as container:
            return await operation(ConsoleContext(settings=settings, container=container))
