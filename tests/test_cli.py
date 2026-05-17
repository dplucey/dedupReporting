import json
import tomllib
from pathlib import Path

import pytest

from dedup_scan.cli import main


def test_scan_command_writes_manifest_for_all_files(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "photos"
    root.mkdir()
    (root / "a.txt").write_text("alpha", encoding="utf-8")
    (root / "b.txt").write_text("bravo", encoding="utf-8")
    manifest_path = tmp_path / "scan.jsonl"

    exit_code = main(["scan", str(root), "--manifest", str(manifest_path)])

    assert exit_code == 0
    assert capsys.readouterr().err == ""
    rows = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines()]
    assert {row["relative_path"] for row in rows} == {"a.txt", "b.txt"}
    assert {row["status"] for row in rows} == {"ok"}
    assert all(row["algorithm"] == "sha256" for row in rows)


def test_scan_command_rejects_manifest_inside_scan_root(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "photos"
    root.mkdir()
    (root / "a.txt").write_text("alpha", encoding="utf-8")
    manifest_path = root / "manifest.jsonl"

    exit_code = main(["scan", str(root), "--manifest", str(manifest_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "manifest path must be outside scan roots" in captured.err
    assert "Traceback" not in captured.err
    assert not manifest_path.exists()
    assert sorted(path.name for path in root.iterdir()) == ["a.txt"]


def test_report_command_reads_multiple_manifests_and_prints_duplicates(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    (first_root / "a.txt").write_text("same", encoding="utf-8")
    (second_root / "a-copy.txt").write_text("same", encoding="utf-8")
    first_manifest = tmp_path / "first.jsonl"
    second_manifest = tmp_path / "second.jsonl"
    assert main(["scan", str(first_root), "--manifest", str(first_manifest)]) == 0
    assert main(["scan", str(second_root), "--manifest", str(second_manifest)]) == 0

    exit_code = main(["report", str(first_manifest), str(second_manifest), "--format", "text"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "sha256 " in captured.out
    assert str(first_root / "a.txt") in captured.out
    assert str(second_root / "a-copy.txt") in captured.out


def test_cli_errors_are_generic_without_stack_traces(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["report", "missing.jsonl"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "error:" in captured.err
    assert "Traceback" not in captured.err


def test_scan_command_wires_interrupt_signal_to_scan_service(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "photos"
    root.mkdir()
    (root / "a.txt").write_text("alpha", encoding="utf-8")
    manifest_path = tmp_path / "scan.jsonl"
    stop_signal = ManualStopSignal(is_set=True)

    exit_code = main(
        ["scan", str(root), "--manifest", str(manifest_path)],
        stop_signal=stop_signal,
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "stopped" in captured.err
    assert "Traceback" not in captured.err


def test_project_declares_dedup_scan_console_script() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"]["dedup-scan"] == "dedup_scan.cli:main"


class ManualStopSignal:
    def __init__(self, *, is_set: bool = False) -> None:
        self._is_set = is_set

    def is_set(self) -> bool:
        return self._is_set
