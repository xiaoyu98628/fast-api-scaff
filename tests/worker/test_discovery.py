"""验证 QueueJob 自动发现的模块边界、筛选规则和失败语义。"""

from collections.abc import Callable
from types import ModuleType, SimpleNamespace
from typing import cast

import pytest

import app.interfaces.worker.discovery as discovery_module
from app.infrastructure.queue.errors import QueueConfigurationError
from app.infrastructure.queue.job import QueueJob
from app.interfaces.worker.context import JobExecutionContext

type WorkerJobType = type[QueueJob[JobExecutionContext]]


def _package(name: str) -> ModuleType:
    """构造具有最小包属性的发现根。"""

    package = ModuleType(name)
    package.__path__ = []
    return package


def _concrete_job(name: str, module_name: str) -> WorkerJobType:
    """构造直接定义在指定模块中的具体测试任务。"""

    async def handle(self: QueueJob[JobExecutionContext], context: JobExecutionContext) -> None:
        del self, context

    return cast(
        WorkerJobType,
        type(name, (QueueJob,), {"__module__": module_name, "handle": handle}),
    )


def _abstract_job(name: str, module_name: str) -> WorkerJobType:
    """构造未实现 handle 的抽象测试任务。"""

    return cast(WorkerJobType, type(name, (QueueJob,), {"__module__": module_name}))


def test_discovery_imports_only_jobs_modules_and_returns_direct_concrete_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _package("example")
    direct_job = _concrete_job("DirectJob", "example.feature.jobs.task")
    imported_job = _concrete_job("ImportedJob", "example.other.jobs.imported")
    abstract_job = _abstract_job("AbstractJob", "example.feature.jobs.abstract")
    modules: dict[str, ModuleType] = {}

    task_module = ModuleType("example.feature.jobs.task")
    setattr(task_module, "DirectJob", direct_job)
    setattr(task_module, "ImportedJob", imported_job)
    modules[task_module.__name__] = task_module

    abstract_module = ModuleType("example.feature.jobs.abstract")
    setattr(abstract_module, "AbstractJob", abstract_job)
    modules[abstract_module.__name__] = abstract_module

    module_names = (
        "example.feature.jobs.task",
        "example.feature.not_jobs.task",
        "example.feature.jobs.abstract",
        "external.jobs.task",
    )
    monkeypatch.setattr(
        discovery_module.pkgutil,
        "walk_packages",
        lambda *_args, **_kwargs: iter(SimpleNamespace(name=name) for name in module_names),
    )
    imported_names: list[str] = []

    def import_module(name: str) -> ModuleType:
        imported_names.append(name)
        return modules[name]

    monkeypatch.setattr(discovery_module.importlib, "import_module", import_module)

    assert discovery_module.discover_job_types(root) == (direct_job,)
    assert imported_names == [
        "example.feature.jobs.abstract",
        "example.feature.jobs.task",
    ]


def test_production_discovery_finds_user_jobs() -> None:
    from app.contexts.user.jobs.cleanup_expired_sessions import CleanupExpiredSessionsJob
    from app.contexts.user.jobs.login_succeeded import LoginSucceededJob

    assert discovery_module.discover_job_types() == (CleanupExpiredSessionsJob, LoginSucceededJob)


def test_discovery_rejects_non_package_root() -> None:
    with pytest.raises(QueueConfigurationError, match="发现根必须是 Python 包"):
        discovery_module.discover_job_types(ModuleType("example"))


def test_discovery_does_not_silently_skip_package_import_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    root = _package("example")

    def fail_package(*_args: object, **kwargs: object) -> tuple[()]:
        onerror = cast(Callable[[str], None], kwargs["onerror"])
        onerror("example.feature")
        return ()

    monkeypatch.setattr(discovery_module.pkgutil, "walk_packages", fail_package)

    with pytest.raises(QueueConfigurationError, match="example.feature.*导入失败"):
        discovery_module.discover_job_types(root)


def test_discovery_wraps_candidate_module_import_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    root = _package("example")
    monkeypatch.setattr(
        discovery_module.pkgutil,
        "walk_packages",
        lambda *_args, **_kwargs: iter((SimpleNamespace(name="example.feature.jobs.broken"),)),
    )

    def fail_import(name: str) -> ModuleType:
        raise RuntimeError(name)

    monkeypatch.setattr(discovery_module.importlib, "import_module", fail_import)

    with pytest.raises(QueueConfigurationError, match="example.feature.jobs.broken.*导入失败") as captured:
        discovery_module.discover_job_types(root)

    assert isinstance(captured.value.__cause__, RuntimeError)
