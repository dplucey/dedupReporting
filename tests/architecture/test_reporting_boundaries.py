from dedup_scan.domain.records import FileHashRecord
from dedup_scan.infrastructure.unique_reporters import render_unique_json_report, render_unique_text_report
from dedup_scan.service.reporting import duplicate_groups
from dedup_scan.service.unique_compare import unique_to_target


def test_reporting_uses_manifest_records_without_filesystem_access() -> None:
    records = (
        _record(path="/does/not/exist/a.txt", digest="same"),
        _record(path="/also/missing/a-copy.txt", digest="same"),
    )

    groups = duplicate_groups(records)

    assert len(groups) == 1
    assert [record.path for record in groups[0].records] == [
        "/does/not/exist/a.txt",
        "/also/missing/a-copy.txt",
    ]


def test_unique_compare_uses_manifest_records_without_filesystem_access() -> None:
    incoming = (_record(path="/does/not/exist/new.txt", digest="new"),)
    target = (_record(path="/also/missing/existing.txt", digest="existing"),)

    report = unique_to_target(incoming_records=incoming, target_records=target)
    text_report = render_unique_text_report(report)
    json_report = render_unique_json_report(report)

    assert "/does/not/exist/new.txt" in text_report
    assert "/does/not/exist/new.txt" in json_report


def _record(*, path: str, digest: str) -> FileHashRecord:
    return FileHashRecord(
        scan_id="scan-1",
        root_path="/does/not/exist",
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
