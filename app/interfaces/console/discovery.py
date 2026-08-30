import importlib
import inspect
import pkgutil

import app.interfaces.console.commands as commands_package
from app.interfaces.console.application import ConsoleApplication
from app.interfaces.console.command import ConsoleCommand


def discover_console_commands(console: ConsoleApplication) -> tuple[ConsoleCommand, ...]:
    """扫描 commands 包并实例化其中定义的具体命令类。"""
    command_types: list[type[ConsoleCommand]] = []
    prefix = f"{commands_package.__name__}."

    for module_info in pkgutil.walk_packages(commands_package.__path__, prefix=prefix):
        module = importlib.import_module(module_info.name)

        for _, candidate in inspect.getmembers(module, inspect.isclass):
            if not issubclass(candidate, ConsoleCommand):
                continue

            if candidate is ConsoleCommand or candidate.__module__ != module.__name__ or inspect.isabstract(candidate):
                continue

            command_types.append(candidate)

    command_types.sort(key=lambda command_type: (command_type.group, command_type.name))
    return tuple(command_type(console) for command_type in command_types)
