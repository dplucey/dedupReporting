from dedup_scan.domain.records import FileHashRecord
from dedup_scan.service.reporting import duplicate_groups


def test_groups_duplicate_hashes_across_different_scan_ids() -> None:
    records = (
        _ok_record(scan_id="scan-1", path="/data/photos/a.jpg", digest="same"),
        _ok_record(scan_id="scan-2", path="/data/archive/a.jpg", digest="same"),
    )

    groups = duplicate_groups(records)

    assert len(groups) == 1
    assert groups[0].algorithm == "sha256"
    assert groups[0].digest == "same"
    assert [record.scan_id for record in groups[0].records] == ["scan-1", "scan-2"]


def test_duplicate_report_ignores_error_records_and_singletons() -> None:
    records = (
        _ok_record(scan_id="scan-1", path="/data/a.txt", digest="same"),
        _ok_record(scan_id="scan-1", path="/data/b.txt", digest="unique"),
        _error_record(scan_id="scan-1", path="/data/private.bin"),
        _ok_record(scan_id="scan-2", path="/archive/a.txt", digest="same"),
    )

    groups = duplicate_groups(records)

    assert len(groups) == 1
    assert groups[0].digest == "same"
    assert [record.path for record in groups[0].records] == ["/data/a.txt", "/archive/a.txt"]


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


def _error_record(*, scan_id: str, path: str) -> FileHashRecord:
    return FileHashRecord(
        scan_id=scan_id,
        root_path="/data",
        path=path,
        relative_path=path.removeprefix("/data/"),
        size_bytes=None,
        mtime_ns=None,
        algorithm="sha256",
        digest=None,
        status="error",
        error="permission denied",
        scanned_at="2026-05-17T12:00:00Z",
    )
