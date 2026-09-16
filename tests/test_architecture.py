"""验证模块依赖方向、绝对导入和基础设施驱动边界。"""

import ast
from collections.abc import Iterator
from pathlib import Path
from sys import stdlib_module_names

from app.runtime.paths import PROJECT_ROOT

_CONTEXTS_ROOT = PROJECT_ROOT / "app/contexts"
_APP_ROOT = PROJECT_ROOT / "app"


def test_application_modules_use_absolute_imports() -> None:
    violations: list[str] = []

    for source_path in sorted(_APP_ROOT.rglob("*.py")):
        source = source_path.read_text(encoding="utf-8")
        for module, line in _iter_imports(ast.parse(source, filename=str(source_path))):
            if module != "<relative import>":
                continue

            relative_path = source_path.relative_to(PROJECT_ROOT)
            violations.append(f"{relative_path}:{line} uses a relative import")

    assert violations == []


def test_domain_layers_only_depend_on_their_own_domain() -> None:
    violations = _find_dependency_violations("domain", allowed_layers=("domain",))

    assert violations == []


def test_application_layers_only_depend_on_their_own_application_and_domain() -> None:
    violations = _find_dependency_violations("application", allowed_layers=("application", "domain"))

    assert violations == []


def test_httpx2_is_confined_to_outbound_http_driver() -> None:
    violations: list[str] = []
    allowed_root = _APP_ROOT / "infrastructure/http/drivers/httpx2"

    for source_path in sorted(_APP_ROOT.rglob("*.py")):
        if source_path.is_relative_to(allowed_root):
            continue

        source = source_path.read_text(encoding="utf-8")
        for module, line in _iter_imports(ast.parse(source, filename=str(source_path))):
            if module == "httpx2" or module.startswith("httpx2."):
                relative_path = source_path.relative_to(PROJECT_ROOT)
                violations.append(f"{relative_path}:{line} imports {module}")

    assert violations == []


def test_shared_infrastructure_does_not_depend_on_business_or_host_layers() -> None:
    violations = _find_forbidden_dependencies(
        _APP_ROOT / "infrastructure",
        forbidden_prefixes=("app.bootstrap", "app.contexts", "app.interfaces"),
    )

    assert violations == []


def test_context_infrastructure_does_not_cross_context_or_depend_on_hosts() -> None:
    violations: list[str] = []
    context_names = tuple(path.name for path in _context_directories())

    for context_name in context_names:
        forbidden_prefixes = (
            "app.bootstrap",
            "app.interfaces",
            f"app.contexts.{context_name}.composition",
            *(f"app.contexts.{other_name}" for other_name in context_names if other_name != context_name),
        )
        violations.extend(
            _find_forbidden_dependencies(
                _CONTEXTS_ROOT / context_name / "infrastructure",
                forbidden_prefixes=forbidden_prefixes,
            )
        )

    assert violations == []


def test_context_composition_does_not_cross_context_or_depend_on_hosts() -> None:
    violations: list[str] = []
    context_names = tuple(path.name for path in _context_directories())

    for context_name in context_names:
        forbidden_prefixes = (
            "app.bootstrap",
            "app.interfaces",
            *(f"app.contexts.{other_name}" for other_name in context_names if other_name != context_name),
        )
        violations.extend(
            _find_forbidden_dependencies(
                _CONTEXTS_ROOT / context_name / "composition.py",
                forbidden_prefixes=forbidden_prefixes,
            )
        )

    assert violations == []


def test_jobs_modules_keep_the_worker_adapter_boundary() -> None:
    """Job 可用宿主公共能力，但不能反向依赖组合根、驱动或其他上下文实现。"""

    violations: list[str] = []
    context_names = tuple(path.name for path in _context_directories())

    for source_path in _job_source_paths():
        relative_parts = source_path.relative_to(_APP_ROOT).parts
        context_name = relative_parts[1] if len(relative_parts) > 2 and relative_parts[0] == "contexts" else None
        forbidden_prefixes = (
            "app.bootstrap",
            "app.infrastructure.queue.drivers",
            *(f"app.contexts.{other_name}.infrastructure" for other_name in context_names if other_name != context_name),
        )
        violations.extend(_find_forbidden_dependencies(source_path, forbidden_prefixes=forbidden_prefixes))

        source = source_path.read_text(encoding="utf-8")
        for module, line in _iter_imports(ast.parse(source, filename=str(source_path))):
            if module.split(".", maxsplit=1)[0] not in {"redis", "aiokafka", "aio_pika"}:
                continue
            relative_path = source_path.relative_to(PROJECT_ROOT)
            violations.append(f"{relative_path}:{line} imports {module}")

    assert violations == []


def test_interfaces_do_not_depend_on_context_persistence_ports() -> None:
    forbidden_prefixes: list[str] = []

    for context_directory in _context_directories():
        context_root = f"app.contexts.{context_directory.name}"
        forbidden_prefixes.extend(
            (
                f"{context_root}.infrastructure",
                f"{context_root}.domain.repository",
                f"{context_root}.application.unit_of_work",
            )
        )

    violations = _find_forbidden_dependencies(
        _APP_ROOT / "interfaces",
        forbidden_prefixes=tuple(forbidden_prefixes),
    )

    assert violations == []


def test_interfaces_do_not_depend_on_bootstrap() -> None:
    violations = _find_forbidden_dependencies(
        _APP_ROOT / "interfaces",
        forbidden_prefixes=("app.bootstrap",),
    )

    assert violations == []


def _find_dependency_violations(layer: str, *, allowed_layers: tuple[str, ...]) -> list[str]:
    violations: list[str] = []

    for context_directory in _context_directories():
        layer_directory = context_directory / layer
        if not layer_directory.is_dir():
            continue

        allowed_prefixes = tuple(f"app.contexts.{context_directory.name}.{name}" for name in allowed_layers)
        for source_path in sorted(layer_directory.rglob("*.py")):
            source = source_path.read_text(encoding="utf-8")
            for module, line in _iter_imports(ast.parse(source, filename=str(source_path))):
                if _is_allowed_dependency(module, allowed_prefixes):
                    continue

                relative_path = source_path.relative_to(PROJECT_ROOT)
                violations.append(f"{relative_path}:{line} imports {module}")

    return violations


def _context_directories() -> tuple[Path, ...]:
    return tuple(sorted(path for path in _CONTEXTS_ROOT.iterdir() if path.is_dir() and (path / "__init__.py").is_file()))


def _job_source_paths() -> tuple[Path, ...]:
    """返回模块路径中含独立 jobs 段的全部 Python 源文件。"""

    paths: list[Path] = []
    for source_path in sorted(_APP_ROOT.rglob("*.py")):
        relative_path = source_path.relative_to(_APP_ROOT)
        module_parts = (*relative_path.parent.parts, relative_path.stem)
        if "jobs" in module_parts:
            paths.append(source_path)
    return tuple(paths)


def _find_forbidden_dependencies(source_root: Path, *, forbidden_prefixes: tuple[str, ...]) -> list[str]:
    violations: list[str] = []

    if source_root.is_file():
        source_paths = (source_root,)
    elif source_root.is_dir():
        source_paths = tuple(sorted(source_root.rglob("*.py")))
    else:
        return violations

    for source_path in source_paths:
        source = source_path.read_text(encoding="utf-8")
        for module, line in _iter_imports(ast.parse(source, filename=str(source_path))):
            if not any(module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden_prefixes):
                continue

            relative_path = source_path.relative_to(PROJECT_ROOT)
            violations.append(f"{relative_path}:{line} imports {module}")

    return violations


def _iter_imports(tree: ast.AST) -> Iterator[tuple[str, int]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom):
            module = node.module if node.level == 0 and node.module is not None else "<relative import>"
            yield module, node.lineno


def _is_allowed_dependency(module: str, allowed_prefixes: tuple[str, ...]) -> bool:
    if module.split(".", maxsplit=1)[0] in stdlib_module_names:
        return True

    return any(module == prefix or module.startswith(f"{prefix}.") for prefix in allowed_prefixes)


def test_http_does_not_import_worker_host() -> None:
    assert _find_forbidden_dependencies(_APP_ROOT / "interfaces/http", forbidden_prefixes=("app.interfaces.worker",)) == []


def test_queue_clients_are_confined_to_drivers() -> None:
    violations: list[str] = []
    for path in sorted(_APP_ROOT.rglob("*.py")):
        if path.is_relative_to(_APP_ROOT / "infrastructure/queue/drivers"):
            continue
        for module, line in _iter_imports(ast.parse(path.read_text(encoding="utf-8"))):
            if module.split(".")[0] in {"aiokafka", "aio_pika"}:
                violations.append(f"{path.relative_to(PROJECT_ROOT)}:{line} imports {module}")
    assert violations == []


def test_vector_sdks_are_confined_to_vector_drivers() -> None:
    violations: list[str] = []
    allowed_root = _APP_ROOT / "infrastructure/vector/drivers"

    for path in sorted(_APP_ROOT.rglob("*.py")):
        if path.is_relative_to(allowed_root):
            continue
        for module, line in _iter_imports(ast.parse(path.read_text(encoding="utf-8"))):
            if module.split(".")[0] in {"chromadb", "elastic_transport", "elasticsearch", "pymilvus"}:
                violations.append(f"{path.relative_to(PROJECT_ROOT)}:{line} imports {module}")

    assert violations == []


def test_cache_does_not_depend_on_scenario_components() -> None:
    assert (
        _find_forbidden_dependencies(
            _APP_ROOT / "infrastructure/cache",
            forbidden_prefixes=("app.contexts", "app.interfaces", "app.infrastructure.rate_limit"),
        )
        == []
    )


def test_scenario_scripts_are_owned_outside_cache() -> None:
    # 防止将场景策略重新塞回通用缓存；脚本资源目录不是 Python 包。
    assert list((_APP_ROOT / "infrastructure/cache").rglob("*.lua")) == []
    for relative in (
        "contexts/user/infrastructure/security/scripts/increment_with_ttl.lua",
        "contexts/user/infrastructure/security/scripts/delete_below.lua",
        "infrastructure/rate_limit/scripts/acquire_window.lua",
    ):
        assert (_APP_ROOT / relative).is_file()
