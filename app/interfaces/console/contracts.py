from collections.abc import Awaitable, Callable
from typing import Protocol

from app.config.settings import Settings
from app.interfaces.console.context import ConsoleContext
from app.interfaces.console.presentation import ConsolePresenter

type SettingsLoader = Callable[[], Settings]
type ConsoleOperation[T] = Callable[[ConsoleContext], Awaitable[T]]


class ConsoleExecutor(Protocol):
    @property
    def settings_loader(self) -> SettingsLoader: ...

    @property
    def presenter(self) -> ConsolePresenter: ...

    def run[T](self, operation: ConsoleOperation[T]) -> T: ...
