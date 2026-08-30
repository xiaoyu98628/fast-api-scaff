import typer

from app.interfaces.console.command import ConsoleCommand


class ConsoleCommandRegistry:
    """创建命令组并校验、注册自动发现的 Console 命令。"""

    def __init__(self, application: typer.Typer) -> None:
        self._application = application
        self._groups: dict[str, typer.Typer] = {}
        self._group_help: dict[str, str] = {}
        self._commands: set[tuple[str, str]] = set()

    def register(self, command: ConsoleCommand) -> None:
        command_key = (command.group, command.name)
        if command_key in self._commands:
            raise RuntimeError(f"Console 命令重复：{command.group} {command.name}")

        group = self._resolve_group(command)
        command.register(group)
        self._commands.add(command_key)

    def _resolve_group(self, command: ConsoleCommand) -> typer.Typer:
        group = self._groups.get(command.group)
        if group is not None:
            if self._group_help[command.group] != command.group_help:
                raise RuntimeError(f"Console 命令组 {command.group!r} 的帮助文本不一致")

            return group

        group = typer.Typer(help=command.group_help)
        self._groups[command.group] = group
        self._group_help[command.group] = command.group_help
        self._application.add_typer(group, name=command.group)
        return group
