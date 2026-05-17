from pathlib import Path

from dedup_scan.cli import _build_parser


def test_readme_scan_and_report_commands_match_cli_parser() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    commands = [
        line.removeprefix("$ ").strip()
        for line in readme.splitlines()
        if line.startswith("$ .venv/bin/python -m dedup_scan.cli ")
    ]

    assert commands == [
        ".venv/bin/python -m dedup_scan.cli scan /data/photos --manifest manifests/photos.jsonl",
        ".venv/bin/python -m dedup_scan.cli report manifests/photos.jsonl manifests/archive.jsonl --format text",
        ".venv/bin/python -m dedup_scan.cli report manifests/photos.jsonl --format json",
    ]

    parser = _build_parser()
    for command in commands:
        parser.parse_args(command.split()[3:])
