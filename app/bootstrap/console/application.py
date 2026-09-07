import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial

from app.bootstrap.build import build_application_container
from app.bootstrap.console.logging import configure_console_logging
from app.config.settings import Settings, load_settings
from app.interfaces.console.context import ConsoleContext
from app.interfaces.console.contracts import ConsoleOperation
from app.interfaces.console.presentation import ConsolePresenter
from app.runtime.container import ApplicationContainer
from app.runtime.lifecycle import ApplicationRuntime

type SettingsLoader = Callable[[], Settings]
type ContainerBuilder = Callable[[Settings], ApplicationContainer]
type LoggingConfigurer = Callable[[Settings], None]


@dataclass(frozen=True, slots=True)
class ConsoleHost:
    """在一次性进程中执行依赖应用容器的操作。"""

    settings_loader: SettingsLoader = load_settings
    container_builder: ContainerBuilder = build_application_container
    logging_configurer: LoggingConfigurer = configure_console_logging
    presenter: ConsolePresenter = field(default_factory=ConsolePresenter)

    def run[T](self, operation: ConsoleOperation[T]) -> T:
        settings = self.settings_loader()
        self.logging_configurer(settings)
        return asyncio.run(self._run(settings, operation))

    async def _run[T](self, settings: Settings, operation: ConsoleOperation[T]) -> T:
        runtime = ApplicationRuntime(partial(self.container_builder, settings))

        async with runtime as container:
            return await operation(ConsoleContext(settings=settings, container=container))
