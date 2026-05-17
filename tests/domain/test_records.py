import pytest

from dedup_scan.domain.records import DuplicateGroup, FileHashRecord


def test_file_hash_record_requires_digest_for_ok_status() -> None:
    record = FileHashRecord(
        scan_id="2026-05-17T12-00-00Z",
        root_path="/data/photos",
        path="/data/photos/a.jpg",
        relative_path="a.jpg",
        size_bytes=4123456,
        mtime_ns=1779031234000000000,
        algorithm="sha256",
        digest="abc123",
        status="ok",
        error=None,
        scanned_at="2026-05-17T12:00:00Z",
    )

    assert record.digest == "abc123"

    with pytest.raises(ValueError, match="ok records require digest"):
        FileHashRecord(
            scan_id="2026-05-17T12-00-00Z",
            root_path="/data/photos",
            path="/data/photos/a.jpg",
            relative_path="a.jpg",
            size_bytes=4123456,
            mtime_ns=1779031234000000000,
            algorithm="sha256",
            digest=None,
            status="ok",
            error=None,
            scanned_at="2026-05-17T12:00:00Z",
        )


def test_file_hash_record_rejects_digest_for_error_status() -> None:
    with pytest.raises(ValueError, match="error records must not include digest"):
        FileHashRecord(
            scan_id="2026-05-17T12-00-00Z",
            root_path="/data/photos",
            path="/data/photos/private.bin",
            relative_path="private.bin",
            size_bytes=None,
            mtime_ns=None,
            algorithm="sha256",
            digest="abc123",
            status="error",
            error="permission denied",
            scanned_at="2026-05-17T12:00:00Z",
        )


def test_duplicate_group_is_immutable_and_counts_records() -> None:
    first = FileHashRecord(
        scan_id="scan-1",
        root_path="/data/photos",
        path="/data/photos/a.jpg",
        relative_path="a.jpg",
        size_bytes=12,
        mtime_ns=100,
        algorithm="sha256",
        digest="same",
        status="ok",
        error=None,
        scanned_at="2026-05-17T12:00:00Z",
    )
    second = FileHashRecord(
        scan_id="scan-2",
        root_path="/data/archive",
        path="/data/archive/a.jpg",
        relative_path="a.jpg",
        size_bytes=12,
        mtime_ns=200,
        algorithm="sha256",
        digest="same",
        status="ok",
        error=None,
        scanned_at="2026-05-17T12:01:00Z",
    )

    group = DuplicateGroup(algorithm="sha256", digest="same", records=(first, second))

    assert group.count == 2
    with pytest.raises(AttributeError):
        group.digest = "different"  # type: ignore[misc]
