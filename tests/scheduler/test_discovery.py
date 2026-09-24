"""验证定时计划自动发现的模块边界、顺序和失败语义。"""

from collections.abc import Callable
from dataclasses import dataclass
from types import ModuleType, SimpleNamespace
from typing import cast

import pytest

import app.interfaces.scheduler.discovery as discovery_module
from app.contexts.user.jobs.cleanup_expired_sessions import CleanupExpiredSessionsJob
from app.infrastructure.queue.job import QueueJob
from app.interfaces.scheduler.contracts import CronSchedule, QueueJobSchedule
from app.interfaces.scheduler.errors import SchedulerConfigurationError
from app.interfaces.scheduler.registry import ScheduleRegistry


@dataclass(frozen=True, slots=True)
class ExampleJob(QueueJob[object]):
    """提供发现测试使用的最小可编码任务。"""

    async def handle(self, context: object) -> None:
        """满足 QueueJob 执行契约。"""

        del context


def _package(name: str) -> ModuleType:
    """构造具有最小包属性的发现根。"""

    package = ModuleType(name)
    package.__path__ = []
    return package


def _schedule_module(name: str, registrar: Callable[[ScheduleRegistry], None] | None = None) -> ModuleType:
    """构造可选含直接注册函数的计划模块。"""

    module = ModuleType(name)
    if registrar is not None:
        registrar.__module__ = name
        setattr(module, "register_schedules", registrar)
    return module


def _definition(schedule_id: str, hour: int = 0) -> QueueJobSchedule:
    """构造发现测试使用的最小计划。"""

    return QueueJobSchedule(
        id=schedule_id,
        trigger=CronSchedule(hour=hour),
        job=ExampleJob(),
    )


def test_discovery_imports_only_schedule_modules_in_stable_order(monkeypatch: pytest.MonkeyPatch) -> None:
    root = _package("example")
    registration_order: list[str] = []

    def register_first(registry: ScheduleRegistry) -> None:
        registration_order.append("first")
        registry.add(_definition("reports.first", 1))

    def register_second(registry: ScheduleRegistry) -> None:
        registration_order.append("second")
        registry.add(_definition("reports.second", 2))

    modules = {
        "example.feature.schedules.first": _schedule_module(
            "example.feature.schedules.first",
            register_first,
        ),
        "example.feature.schedules.helpers": _schedule_module("example.feature.schedules.helpers"),
        "example.feature.schedules.second": _schedule_module(
            "example.feature.schedules.second",
            register_second,
        ),
    }
    module_names = (
        "example.feature.schedules.second",
        "example.feature.jobs.task",
        "example.feature.schedules",
        "external.schedules.task",
        "example.feature.schedules.helpers",
        "example.feature.schedules.first",
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

    registry = discovery_module.discover_schedule_registry(root)

    assert imported_names == [
        "example.feature.schedules.first",
        "example.feature.schedules.helpers",
        "example.feature.schedules.second",
    ]
    assert registration_order == ["first", "second"]
    assert [definition.id for definition in registry.definitions] == ["reports.first", "reports.second"]


def test_production_discovery_finds_midnight_expired_session_cleanup() -> None:
    definitions = discovery_module.discover_schedule_registry().definitions

    assert len(definitions) == 1
    definition = definitions[0]
    assert definition.id == "users.sessions.cleanup_expired"
    assert definition.trigger == CronSchedule(hour=0, minute=0)
    assert definition.job == CleanupExpiredSessionsJob()
    assert definition.connection is None
    assert definition.queue is None


def test_discovery_rejects_non_package_root() -> None:
    with pytest.raises(SchedulerConfigurationError, match="发现根必须是 Python 包"):
        discovery_module.discover_schedule_registry(ModuleType("example"))


def test_discovery_does_not_silently_skip_package_import_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    root = _package("example")

    def fail_package(*_args: object, **kwargs: object) -> tuple[()]:
        onerror = cast(Callable[[str], None], kwargs["onerror"])
        onerror("example.feature")
        return ()

    monkeypatch.setattr(discovery_module.pkgutil, "walk_packages", fail_package)

    with pytest.raises(SchedulerConfigurationError, match="example.feature.*导入失败"):
        discovery_module.discover_schedule_registry(root)


def test_discovery_wraps_candidate_module_import_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    root = _package("example")
    monkeypatch.setattr(
        discovery_module.pkgutil,
        "walk_packages",
        lambda *_args, **_kwargs: iter((SimpleNamespace(name="example.feature.schedules.broken"),)),
    )

    def fail_import(name: str) -> ModuleType:
        raise RuntimeError(name)

    monkeypatch.setattr(discovery_module.importlib, "import_module", fail_import)

    with pytest.raises(SchedulerConfigurationError, match="schedules.broken.*导入失败") as captured:
        discovery_module.discover_schedule_registry(root)

    assert isinstance(captured.value.__cause__, RuntimeError)


def test_discovery_reports_duplicate_id_as_registration_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    root = _package("example")

    def register_first(registry: ScheduleRegistry) -> None:
        registry.add(_definition("reports.duplicate", 1))

    def register_second(registry: ScheduleRegistry) -> None:
        registry.add(_definition("reports.duplicate", 2))

    modules = {
        "example.feature.schedules.first": _schedule_module(
            "example.feature.schedules.first",
            register_first,
        ),
        "example.feature.schedules.second": _schedule_module(
            "example.feature.schedules.second",
            register_second,
        ),
    }
    monkeypatch.setattr(
        discovery_module.pkgutil,
        "walk_packages",
        lambda *_args, **_kwargs: iter(SimpleNamespace(name=name) for name in reversed(modules)),
    )
    monkeypatch.setattr(discovery_module.importlib, "import_module", lambda name: modules[name])

    with pytest.raises(SchedulerConfigurationError, match="schedules.second.*注册失败") as captured:
        discovery_module.discover_schedule_registry(root)

    assert isinstance(captured.value.__cause__, ValueError)


def test_discovery_rejects_registrar_imported_from_another_module(monkeypatch: pytest.MonkeyPatch) -> None:
    root = _package("example")

    def register_schedules(registry: ScheduleRegistry) -> None:
        del registry

    module = ModuleType("example.feature.schedules.imported")
    setattr(module, "register_schedules", register_schedules)
    monkeypatch.setattr(
        discovery_module.pkgutil,
        "walk_packages",
        lambda *_args, **_kwargs: iter((SimpleNamespace(name=module.__name__),)),
    )
    monkeypatch.setattr(discovery_module.importlib, "import_module", lambda _name: module)

    with pytest.raises(SchedulerConfigurationError, match="必须由当前模块直接定义"):
        discovery_module.discover_schedule_registry(root)
