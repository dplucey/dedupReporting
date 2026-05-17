from pathlib import Path

from dedup_scan.infrastructure.filesystem import walk_regular_files


def test_walk_skips_symlinks_by_default(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    target.write_text("target", encoding="utf-8")
    symlink = tmp_path / "link.txt"
    symlink.symlink_to(target)

    paths = list(walk_regular_files((tmp_path,)))

    assert paths == [target]
