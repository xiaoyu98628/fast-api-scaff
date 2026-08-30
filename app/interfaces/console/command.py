from abc import ABC, abstractmethod
from typing import Any, ClassVar

import typer

from app.interfaces.console.application import ConsoleApplication


class ConsoleCommand(ABC):
    """定义可被 Console 自动发现并注册的命令。"""

    group: ClassVar[str]
    group_help: ClassVar[str]
    name: ClassVar[str]
    help: ClassVar[str]

    def __init__(self, console: ConsoleApplication) -> None:
        self._console = console

    def register(self, group: typer.Typer) -> None:
        """将当前命令注册到所属 Typer 命令组。"""
        group.command(name=self.name, help=self.help)(self.handle)

    @abstractmethod
    def handle(self, *args: Any, **kwargs: Any) -> None:
        """处理命令。"""
