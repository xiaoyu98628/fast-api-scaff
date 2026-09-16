"""按 jobs 模块约定发现 Worker 可以消费的 QueueJob。"""

import importlib
import inspect
import pkgutil
from types import ModuleType
from typing import cast

import app
from app.infrastructure.queue.errors import QueueConfigurationError
from app.infrastructure.queue.job import QueueJob
from app.interfaces.worker.context import JobExecutionContext

type WorkerJobType = type[QueueJob[JobExecutionContext]]


def discover_job_types(root_package: ModuleType = app) -> tuple[WorkerJobType, ...]:
    """发现根包下 jobs 模块中直接定义的具体 QueueJob 类型。"""

    package_name = getattr(root_package, "__name__", "")
    package_paths = getattr(root_package, "__path__", None)
    if not package_name or package_paths is None:
        raise QueueConfigurationError("队列任务发现根必须是 Python 包")

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
                if _is_job_module(package_name, module_info.name)
            }
        )
    except QueueConfigurationError:
        raise
    except Exception as error:
        raise QueueConfigurationError("队列任务模块枚举失败") from error

    job_types: list[WorkerJobType] = []
    for module_name in module_names:
        try:
            module = importlib.import_module(module_name)
        except Exception as error:
            raise QueueConfigurationError(f"队列任务模块 {module_name!r} 导入失败") from error

        for _, candidate in inspect.getmembers(module, inspect.isclass):
            if candidate is QueueJob or not issubclass(candidate, QueueJob):
                continue
            if candidate.__module__ != module.__name__ or inspect.isabstract(candidate):
                continue
            job_types.append(cast(WorkerJobType, candidate))

    job_types.sort(key=lambda job_type: (job_type.__module__, job_type.__qualname__))
    return tuple(job_types)


def _is_job_module(root_name: str, module_name: str) -> bool:
    """只匹配根包之下名称含独立 jobs 段的模块或包。"""

    prefix = f"{root_name}."
    if not module_name.startswith(prefix):
        return False
    relative_parts = module_name.removeprefix(prefix).split(".")
    return "jobs" in relative_parts


def _raise_package_import_error(package_name: str) -> None:
    """把递归枚举时默认会忽略的包导入错误转为启动失败。"""

    raise QueueConfigurationError(f"队列任务发现所需包 {package_name!r} 导入失败")
