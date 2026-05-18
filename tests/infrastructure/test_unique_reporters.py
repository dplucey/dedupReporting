import json

from dedup_scan.domain.records import FileHashRecord
from dedup_scan.domain.unique import SkippedRecordCounts, UniqueContentGroup, UniqueContentReport
from dedup_scan.infrastructure.unique_reporters import (
    render_unique_json_report,
    render_unique_text_report,
)


def test_text_unique_report_marks_duplicate_new_groups_for_inspection() -> None:
    report = UniqueContentReport(
        groups=(
            UniqueContentGroup(
                algorithm="sha256",
                digest="new",
                records=(
                    _ok_record(path="/incoming/a.jpg", relative_path="a.jpg"),
                    _ok_record(path="/incoming/copy/a.jpg", relative_path="copy/a.jpg"),
                ),
            ),
        ),
        skipped=SkippedRecordCounts(incoming_error_records=1, target_error_records=2),
    )

    rendered = render_unique_text_report(report)

    assert rendered == "\n".join(
        (
            "sha256 new (2 files, requires inspection)",
            "  /incoming/a.jpg",
            "  /incoming/copy/a.jpg",
            "",
            "skipped incoming_error_records=1 target_error_records=2",
        )
    )


def test_json_unique_report_is_machine_readable() -> None:
    report = UniqueContentReport(
        groups=(
            UniqueContentGroup(
                algorithm="sha256",
                digest="new",
                records=(_ok_record(path="/incoming/a.jpg", relative_path="a.jpg"),),
            ),
        ),
        skipped=SkippedRecordCounts(incoming_error_records=1, target_error_records=2),
    )

    rendered = render_unique_json_report(report)

    assert json.loads(rendered) == {
        "unique_to_target": [
            {
                "algorithm": "sha256",
                "digest": "new",
                "count": 1,
                "requires_inspection": False,
                "files": [
                    {
                        "scan_id": "incoming-scan",
                        "root_path": "/incoming",
                        "path": "/incoming/a.jpg",
                        "relative_path": "a.jpg",
                        "size_bytes": 12,
                        "mtime_ns": 100,
                    }
                ],
            }
        ],
        "skipped": {
            "incoming_error_records": 1,
            "target_error_records": 2,
        },
    }


def _ok_record(*, path: str, relative_path: str) -> FileHashRecord:
    return FileHashRecord(
        scan_id="incoming-scan",
        root_path="/incoming",
        path=path,
        relative_path=relative_path,
        size_bytes=12,
        mtime_ns=100,
        algorithm="sha256",
        digest="new",
        status="ok",
        error=None,
        scanned_at="2026-05-17T12:00:00Z",
    )
