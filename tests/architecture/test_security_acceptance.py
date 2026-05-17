import ast
import json
from pathlib import Path

from dedup_scan.cli import main


PROJECT_ROOT = Path(__file__).resolve().parents[2]
NETWORK_MODULES = {"http", "socket", "urllib", "requests"}
MUTATION_APIS = {"unlink", "remove", "rename", "chmod", "chown", "rmdir"}


def test_scan_and_report_security_acceptance_criteria_are_enforced(
    tmp_path: Path,
    capsys,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "secret.txt").write_text("restricted-value", encoding="utf-8")
    manifest_path = tmp_path / "manifest.jsonl"

    assert main(["scan", str(root), "--manifest", str(manifest_path)]) == 0
    rows = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines()]
    assert "restricted-value" not in manifest_path.read_text(encoding="utf-8")
    assert "content" not in rows[0]

    assert main(["report", str(manifest_path)]) == 0
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    assert "restricted-value" not in captured.out

    assert _forbidden_imports() == []
    assert _scanned_path_mutation_calls() == []


def _forbidden_imports() -> list[str]:
    violations: list[str] = []
    for source_path in (PROJECT_ROOT / "dedup_scan").rglob("*.py"):
        module = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(module):
            imported = _imported_name(node)
            if imported in NETWORK_MODULES or any(
                imported.startswith(f"{network_module}.") for network_module in NETWORK_MODULES
            ):
                violations.append(f"{source_path.relative_to(PROJECT_ROOT)}: {imported}")
    return violations


def _scanned_path_mutation_calls() -> list[str]:
    violations: list[str] = []
    for relative_path in (
        Path("dedup_scan/cli.py"),
        Path("dedup_scan/service/scanning.py"),
        Path("dedup_scan/service/reporting.py"),
        Path("dedup_scan/infrastructure/filesystem.py"),
        Path("dedup_scan/infrastructure/reporters.py"),
    ):
        source_path = PROJECT_ROOT / relative_path
        module = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(module):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in MUTATION_APIS:
                    violations.append(f"{relative_path}: {node.func.attr}")
    return violations


def _imported_name(node: ast.AST) -> str:
    if isinstance(node, ast.Import):
        return node.names[0].name
    if isinstance(node, ast.ImportFrom) and node.module is not None:
        return node.module
    return ""
