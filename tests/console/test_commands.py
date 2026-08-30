import typer

from app.interfaces.console.application import ConsoleApplication
from app.interfaces.console.command import ConsoleCommand
from app.interfaces.console.discovery import discover_console_commands
from app.interfaces.console.registry import ConsoleCommandRegistry


class FirstCommand(ConsoleCommand):
    group = "testing"
    group_help = "测试命令。"
    name = "first"
    help = "第一个测试命令。"

    def handle(self) -> None:
        pass


class DuplicateCommand(FirstCommand):
    pass


class ConflictingGroupHelpCommand(FirstCommand):
    group_help = "不一致的测试命令说明。"
    name = "second"


def test_discovery_finds_concrete_commands_in_stable_order() -> None:
    commands = discover_console_commands(ConsoleApplication())

    assert [(command.group, command.name) for command in commands] == [
        ("app", "info"),
        ("users", "create"),
        ("users", "list"),
    ]


def test_registry_rejects_duplicate_command() -> None:
    registry = ConsoleCommandRegistry(typer.Typer())
    registry.register(FirstCommand(ConsoleApplication()))

    try:
        registry.register(DuplicateCommand(ConsoleApplication()))
    except RuntimeError as error:
        assert str(error) == "Console 命令重复：testing first"
    else:
        raise AssertionError("重复 Console 命令应当注册失败")


def test_registry_rejects_conflicting_group_help() -> None:
    registry = ConsoleCommandRegistry(typer.Typer())
    registry.register(FirstCommand(ConsoleApplication()))

    try:
        registry.register(ConflictingGroupHelpCommand(ConsoleApplication()))
    except RuntimeError as error:
        assert str(error) == "Console 命令组 'testing' 的帮助文本不一致"
    else:
        raise AssertionError("同一 Console 命令组的帮助文本不一致时应当注册失败")
