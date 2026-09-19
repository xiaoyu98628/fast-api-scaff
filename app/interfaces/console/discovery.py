"""从业务与系统命令包自动发现具体 Console 命令。"""

import importlib
import inspect
import pkgutil

import app.interfaces.console.commands as commands_package
import app.interfaces.console.system as system_package
from app.interfaces.console.command import ConsoleCommand
from app.interfaces.console.contracts import ConsoleExecutor

_COMMAND_PACKAGES = (system_package, commands_package)


def discover_console_commands(console: ConsoleExecutor) -> tuple[ConsoleCommand, ...]:
    """扫描系统与业务命令包并实例化其中定义的具体命令类。"""

    command_types: list[type[ConsoleCommand]] = []
    for command_package in _COMMAND_PACKAGES:
        prefix = f"{command_package.__name__}."
        for module_info in pkgutil.walk_packages(command_package.__path__, prefix=prefix):
            module = importlib.import_module(module_info.name)

            for _, candidate in inspect.getmembers(module, inspect.isclass):
                # 模块可能导入其他类，先排除与命令抽象无关的类型。
                if not issubclass(candidate, ConsoleCommand):
                    continue

                # 只注册定义在当前模块中的具体子类，避免重复发现导入符号和抽象基类。
                if candidate is ConsoleCommand or candidate.__module__ != module.__name__ or inspect.isabstract(candidate):
                    continue

                command_types.append(candidate)

    # 固定顺序让帮助文本和重复注册错误不受文件系统遍历顺序影响。
    command_types.sort(key=lambda command_type: (command_type.group, command_type.name))
    return tuple(command_type(console) for command_type in command_types)
