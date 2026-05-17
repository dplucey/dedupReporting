import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOMAIN_ROOT = PROJECT_ROOT / "dedup_scan" / "domain"

FORBIDDEN_DOMAIN_IMPORTS = {
    "argparse",
    "datetime",
    "json",
    "os",
    "pathlib",
    "subprocess",
    "sys",
    "time",
    "dedup_scan.cli",
    "dedup_scan.infrastructure",
    "dedup_scan.service",
}


def test_domain_does_not_import_outer_layers_or_io_modules() -> None:
    violations: list[str] = []

    for source_path in DOMAIN_ROOT.rglob("*.py"):
        module = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(module):
            imported_names = _imported_module_names(node)
            for imported_name in imported_names:
                if _is_forbidden(imported_name):
                    relative_path = source_path.relative_to(PROJECT_ROOT)
                    violations.append(f"{relative_path}: {imported_name}")

    assert violations == []


def test_service_layer_does_not_import_infrastructure_adapters() -> None:
    service_root = PROJECT_ROOT / "dedup_scan" / "service"
    violations: list[str] = []

    for source_path in service_root.rglob("*.py"):
        module = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(module):
            for imported_name in _imported_module_names(node):
                if imported_name == "dedup_scan.infrastructure" or imported_name.startswith(
                    "dedup_scan.infrastructure."
                ):
                    relative_path = source_path.relative_to(PROJECT_ROOT)
                    violations.append(f"{relative_path}: {imported_name}")

    assert violations == []


def _imported_module_names(node: ast.AST) -> tuple[str, ...]:
    if isinstance(node, ast.Import):
        return tuple(alias.name for alias in node.names)
    if isinstance(node, ast.ImportFrom) and node.module is not None:
        return (node.module,)
    return ()


def _is_forbidden(imported_name: str) -> bool:
    return any(
        imported_name == forbidden or imported_name.startswith(f"{forbidden}.")
        for forbidden in FORBIDDEN_DOMAIN_IMPORTS
    )
