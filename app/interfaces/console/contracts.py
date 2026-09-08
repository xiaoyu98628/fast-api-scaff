"""声明 Console 命令与宿主之间的窄接口。"""

from collections.abc import Awaitable, Callable
from typing import Protocol

from app.config.settings import Settings
from app.interfaces.console.context import ConsoleContext
from app.interfaces.console.presentation import ConsolePresenter

type ConsoleOperation[T] = Callable[[ConsoleContext], Awaitable[T]]


class ConsoleExecutor(Protocol):
    """向命令暴露配置、输出和应用操作执行能力。"""

    @property
    def settings(self) -> Settings:
        """返回当前进程使用的不可变配置快照。"""

        ...

    @property
    def presenter(self) -> ConsolePresenter:
        """返回遵循标准流约定的输出器。"""

        ...

    def run[T](self, operation: ConsoleOperation[T]) -> T:
        """在应用容器生命周期内同步等待异步操作。"""

        ...
