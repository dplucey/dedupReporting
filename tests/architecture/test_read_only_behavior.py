import stat
from pathlib import Path

from dedup_scan.cli import main


def test_scan_preserves_file_content_mode_and_directory_entries(tmp_path: Path) -> None:
    root = tmp_path / "scan-root"
    root.mkdir()
    target = root / "a.txt"
    target.write_text("alpha", encoding="utf-8")
    target.chmod(0o640)
    before_content = target.read_text(encoding="utf-8")
    before_mode = stat.S_IMODE(target.stat().st_mode)
    before_entries = sorted(path.name for path in root.iterdir())

    manifest_path = tmp_path / "manifest.jsonl"
    assert main(["scan", str(root), "--manifest", str(manifest_path)]) == 0

    assert target.read_text(encoding="utf-8") == before_content
    assert stat.S_IMODE(target.stat().st_mode) == before_mode
    assert sorted(path.name for path in root.iterdir()) == before_entries
