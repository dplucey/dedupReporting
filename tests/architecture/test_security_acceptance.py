import ast
import json
from pathlib import Path

import dedup_scan.cli as cli
from dedup_scan.cli import main
from dedup_scan.domain.records import FileHashRecord
from dedup_scan.domain.unique import SkippedRecordCounts, UniqueContentGroup, UniqueContentReport
from dedup_scan.infrastructure.unique_reporters import render_unique_json_report


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


def test_parallel_scan_preserves_single_manifest_writer_invariant() -> None:
    service_source = (PROJECT_ROOT / "dedup_scan" / "service" / "scanning.py").read_text(
        encoding="utf-8"
    )
    cli_source = (PROJECT_ROOT / "dedup_scan" / "cli.py").read_text(encoding="utf-8")

    assert "write_manifest" not in service_source
    assert cli_source.count("write_manifest(") == 1


def test_interrupted_parallel_scan_does_not_replace_final_manifest(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "a.txt").write_text("alpha", encoding="utf-8")
    manifest_path = tmp_path / "manifest.jsonl"
    stop_signal = ManualStopSignal()

    original_scan_files_parallel = cli.scan_files_parallel

    def stopping_scan_files_parallel(*args, **kwargs):
        for record in original_scan_files_parallel(*args, **kwargs):
            stop_signal.set()
            yield record

    monkeypatch.setattr(cli, "scan_files_parallel", stopping_scan_files_parallel)

    exit_code = main(
        ["scan", str(root), "--manifest", str(manifest_path), "--workers", "2"],
        stop_signal=stop_signal,
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "stopped" in captured.err
    assert "Traceback" not in captured.err
    assert not manifest_path.exists()


def test_unique_compare_security_acceptance_criteria_are_enforced(
    tmp_path: Path,
    capsys,
) -> None:
    incoming_manifest = tmp_path / "incoming.jsonl"
    target_manifest = tmp_path / "target.jsonl"
    incoming_manifest.write_text("not-json\n", encoding="utf-8")
    target_manifest.write_text("", encoding="utf-8")
    json_report = render_unique_json_report(
        UniqueContentReport(
            groups=(
                UniqueContentGroup(
                    algorithm="sha256",
                    digest="new",
                    records=(_record(path="/incoming/secret.txt", digest="new"),),
                ),
            ),
            skipped=SkippedRecordCounts(),
        )
    )

    exit_code = main(
        [
            "unique-to-target",
            str(incoming_manifest),
            "--against",
            str(target_manifest),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Traceback" not in captured.err
    assert "content" not in json.loads(json_report)["unique_to_target"][0]["files"][0]
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
        Path("dedup_scan/service/unique_compare.py"),
        Path("dedup_scan/infrastructure/filesystem.py"),
        Path("dedup_scan/infrastructure/reporters.py"),
        Path("dedup_scan/infrastructure/unique_reporters.py"),
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


def _record(*, path: str, digest: str) -> FileHashRecord:
    return FileHashRecord(
        scan_id="incoming-scan",
        root_path="/incoming",
        path=path,
        relative_path=path.rsplit("/", maxsplit=1)[-1],
        size_bytes=12,
        mtime_ns=100,
        algorithm="sha256",
        digest=digest,
        status="ok",
        error=None,
        scanned_at="2026-05-17T12:00:00Z",
    )


class ManualStopSignal:
    def __init__(self) -> None:
        self._is_set = False

    def set(self) -> None:
        self._is_set = True

    def is_set(self) -> bool:
        return self._is_set
