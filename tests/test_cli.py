import json
import tomllib
from pathlib import Path

import pytest

import dedup_scan.cli as cli
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


def test_scan_command_defaults_to_one_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "photos"
    root.mkdir()
    (root / "a.txt").write_text("alpha", encoding="utf-8")
    manifest_path = tmp_path / "scan.jsonl"
    calls: list[str] = []

    original_scan_files = cli.scan_files

    def tracking_scan_files(*args, **kwargs):
        calls.append("serial")
        return original_scan_files(*args, **kwargs)

    def fail_parallel_scan(*args, **kwargs):
        raise AssertionError("parallel scan should not be used by default")

    monkeypatch.setattr(cli, "scan_files", tracking_scan_files)
    monkeypatch.setattr(cli, "scan_files_parallel", fail_parallel_scan)

    assert main(["scan", str(root), "--manifest", str(manifest_path)]) == 0

    assert calls == ["serial"]


def test_scan_command_rejects_workers_outside_supported_range_without_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "photos"
    root.mkdir()
    manifest_path = tmp_path / "scan.jsonl"

    for workers in ("0", "33"):
        exit_code = main(["scan", str(root), "--manifest", str(manifest_path), "--workers", workers])
        captured = capsys.readouterr()
        assert exit_code == 1
        assert "workers must be between 1 and 32" in captured.err
        assert "Traceback" not in captured.err


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


def test_unique_to_target_command_accepts_multiple_incoming_manifests_against_one_target_manifest(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target_root = tmp_path / "target"
    incoming_root = tmp_path / "incoming"
    extra_incoming_root = tmp_path / "extra-incoming"
    target_root.mkdir()
    incoming_root.mkdir()
    extra_incoming_root.mkdir()
    (target_root / "existing.txt").write_text("same", encoding="utf-8")
    (incoming_root / "existing-copy.txt").write_text("same", encoding="utf-8")
    (incoming_root / "new.txt").write_text("new", encoding="utf-8")
    (extra_incoming_root / "also-new.txt").write_text("also-new", encoding="utf-8")
    target_manifest = tmp_path / "target.jsonl"
    incoming_manifest = tmp_path / "incoming.jsonl"
    extra_incoming_manifest = tmp_path / "extra-incoming.jsonl"
    assert main(["scan", str(target_root), "--manifest", str(target_manifest)]) == 0
    assert main(["scan", str(incoming_root), "--manifest", str(incoming_manifest)]) == 0
    assert main(["scan", str(extra_incoming_root), "--manifest", str(extra_incoming_manifest)]) == 0

    exit_code = main(
        [
            "unique-to-target",
            str(incoming_manifest),
            str(extra_incoming_manifest),
            "--against",
            str(target_manifest),
            "--format",
            "text",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert str(incoming_root / "new.txt") in captured.out
    assert str(extra_incoming_root / "also-new.txt") in captured.out
    assert str(incoming_root / "existing-copy.txt") not in captured.out


def test_unique_to_target_command_requires_exactly_one_against_manifest(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    incoming_manifest = tmp_path / "incoming.jsonl"
    first_target_manifest = tmp_path / "target-1.jsonl"
    second_target_manifest = tmp_path / "target-2.jsonl"
    incoming_manifest.write_text("", encoding="utf-8")
    first_target_manifest.write_text("", encoding="utf-8")
    second_target_manifest.write_text("", encoding="utf-8")

    missing_against = main(["unique-to-target", str(incoming_manifest)])
    missing_captured = capsys.readouterr()
    too_many_targets = main(
        [
            "unique-to-target",
            str(incoming_manifest),
            "--against",
            str(first_target_manifest),
            str(second_target_manifest),
        ]
    )
    too_many_captured = capsys.readouterr()

    assert missing_against != 0
    assert "Traceback" not in missing_captured.err
    assert too_many_targets != 0
    assert "Traceback" not in too_many_captured.err


def test_unique_to_target_command_errors_are_generic_without_stack_traces(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    incoming_manifest = tmp_path / "incoming.jsonl"
    target_manifest = tmp_path / "target.jsonl"
    incoming_manifest.write_text("not-json\n", encoding="utf-8")
    target_manifest.write_text("", encoding="utf-8")

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
    assert "error:" in captured.err
    assert "Traceback" not in captured.err


def test_unique_to_target_command_wires_stop_signal_to_manifest_readers(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    incoming_manifest = tmp_path / "incoming.jsonl"
    target_manifest = tmp_path / "target.jsonl"
    incoming_manifest.write_text("", encoding="utf-8")
    target_manifest.write_text("", encoding="utf-8")
    stop_signal = ManualStopSignal(is_set=True)

    exit_code = main(
        [
            "unique-to-target",
            str(incoming_manifest),
            "--against",
            str(target_manifest),
        ],
        stop_signal=stop_signal,
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "stopped" in captured.err
    assert "Traceback" not in captured.err


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
