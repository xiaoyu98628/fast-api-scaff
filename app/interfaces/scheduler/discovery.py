"""按 schedules 模块约定发现并注册代码计划。"""

import importlib
import pkgutil
from collections.abc import Callable
from types import ModuleType
from typing import cast

import app
from app.interfaces.scheduler.errors import SchedulerConfigurationError
from app.interfaces.scheduler.registry import ScheduleRegistry

type ScheduleRegistrar = Callable[[ScheduleRegistry], None]

_REGISTRAR_NAME = "register_schedules"


def discover_schedule_registry(root_package: ModuleType = app) -> ScheduleRegistry:
    """扫描根包下的 schedules 模块并构建经过校验的计划注册表。"""

    package_name = getattr(root_package, "__name__", "")
    package_paths = getattr(root_package, "__path__", None)
    if not package_name or package_paths is None:
        raise SchedulerConfigurationError("定时计划发现根必须是 Python 包")

    prefix = f"{package_name}."
    try:
        module_names = sorted(
            {
                module_info.name
                for module_info in pkgutil.walk_packages(
                    package_paths,
                    prefix=prefix,
                    onerror=_raise_package_import_error,
                )
                if _is_schedule_module(package_name, module_info.name)
            }
        )
    except SchedulerConfigurationError:
        raise
    except Exception as error:
        raise SchedulerConfigurationError("定时计划模块枚举失败") from error

    registry = ScheduleRegistry()
    for module_name in module_names:
        module = _import_schedule_module(module_name)
        registrar = _find_registrar(module)
        if registrar is None:
            continue
        try:
            registrar(registry)
        except Exception as error:
            raise SchedulerConfigurationError(f"定时计划模块 {module_name!r} 注册失败") from error
    return registry


def _is_schedule_module(root_name: str, module_name: str) -> bool:
    """只匹配根包下 schedules 包内的模块。"""

    prefix = f"{root_name}."
    if not module_name.startswith(prefix):
        return False
    relative_parts = module_name.removeprefix(prefix).split(".")
    return "schedules" in relative_parts[:-1]


def _import_schedule_module(module_name: str) -> ModuleType:
    """导入计划模块，并保留模块名作为安全诊断信息。"""

    try:
        return importlib.import_module(module_name)
    except Exception as error:
        raise SchedulerConfigurationError(f"定时计划模块 {module_name!r} 导入失败") from error


def _find_registrar(module: ModuleType) -> ScheduleRegistrar | None:
    """返回模块直接定义的约定注册函数，并拒绝同名无效对象。"""

    candidate = getattr(module, _REGISTRAR_NAME, None)
    if candidate is None:
        return None
    if not callable(candidate) or getattr(candidate, "__module__", None) != module.__name__:
        raise SchedulerConfigurationError(f"定时计划模块 {module.__name__!r} 的 {_REGISTRAR_NAME} 必须由当前模块直接定义")
    return cast(ScheduleRegistrar, candidate)


def _raise_package_import_error(package_name: str) -> None:
    """把递归枚举时默认会忽略的包导入错误转为启动失败。"""

    raise SchedulerConfigurationError(f"定时计划发现所需包 {package_name!r} 导入失败")
