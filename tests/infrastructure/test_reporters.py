import json

from dedup_scan.domain.records import DuplicateGroup, FileHashRecord
from dedup_scan.infrastructure.reporters import render_json_report, render_text_report


def test_text_report_lists_digest_then_full_paths() -> None:
    report = render_text_report(
        (
            DuplicateGroup(
                algorithm="sha256",
                digest="same",
                records=(
                    _ok_record(scan_id="scan-1", path="/data/photos/a.jpg", digest="same"),
                    _ok_record(scan_id="scan-2", path="/data/archive/a.jpg", digest="same"),
                ),
            ),
        )
    )

    assert report == "\n".join(
        (
            "sha256 same (2 files)",
            "  /data/photos/a.jpg",
            "  /data/archive/a.jpg",
            "",
        )
    )


def test_json_report_is_machine_readable() -> None:
    report = render_json_report(
        (
            DuplicateGroup(
                algorithm="sha256",
                digest="same",
                records=(
                    _ok_record(scan_id="scan-1", path="/data/photos/a.jpg", digest="same"),
                    _ok_record(scan_id="scan-2", path="/data/archive/a.jpg", digest="same"),
                ),
            ),
        )
    )

    assert json.loads(report) == {
        "duplicate_groups": [
            {
                "algorithm": "sha256",
                "digest": "same",
                "count": 2,
                "files": [
                    {
                        "scan_id": "scan-1",
                        "root_path": "/data",
                        "path": "/data/photos/a.jpg",
                        "relative_path": "photos/a.jpg",
                        "size_bytes": 12,
                        "mtime_ns": 100,
                    },
                    {
                        "scan_id": "scan-2",
                        "root_path": "/data",
                        "path": "/data/archive/a.jpg",
                        "relative_path": "archive/a.jpg",
                        "size_bytes": 12,
                        "mtime_ns": 100,
                    },
                ],
            }
        ]
    }


def _ok_record(*, scan_id: str, path: str, digest: str) -> FileHashRecord:
    return FileHashRecord(
        scan_id=scan_id,
        root_path="/data",
        path=path,
        relative_path=path.removeprefix("/data/"),
        size_bytes=12,
        mtime_ns=100,
        algorithm="sha256",
        digest=digest,
        status="ok",
        error=None,
        scanned_at="2026-05-17T12:00:00Z",
    )
