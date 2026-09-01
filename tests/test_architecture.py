import ast
from collections.abc import Iterator
from sys import stdlib_module_names

from app.runtime.paths import PROJECT_ROOT

_CONTEXTS_ROOT = PROJECT_ROOT / "app/contexts"


def test_domain_layers_only_depend_on_their_own_domain() -> None:
    violations = _find_dependency_violations("domain", allowed_layers=("domain",))

    assert violations == []


def test_application_layers_only_depend_on_their_own_application_and_domain() -> None:
    violations = _find_dependency_violations("application", allowed_layers=("application", "domain"))

    assert violations == []


def _find_dependency_violations(layer: str, *, allowed_layers: tuple[str, ...]) -> list[str]:
    violations: list[str] = []

    for context_directory in sorted(path for path in _CONTEXTS_ROOT.iterdir() if path.is_dir()):
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
