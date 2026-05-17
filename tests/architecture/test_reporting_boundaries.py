from dedup_scan.domain.records import FileHashRecord
from dedup_scan.service.reporting import duplicate_groups


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
