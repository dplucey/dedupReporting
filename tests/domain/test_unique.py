import pytest

from dedup_scan.domain.records import FileHashRecord
from dedup_scan.domain.unique import UniqueContentGroup


def test_unique_content_group_flags_duplicate_new_records_for_inspection() -> None:
    first = _ok_record(path="/incoming/a.jpg", relative_path="a.jpg")
    second = _ok_record(path="/incoming/copy/a.jpg", relative_path="copy/a.jpg")

    single = UniqueContentGroup(algorithm="sha256", digest="new", records=(first,))
    duplicate_new = UniqueContentGroup(
        algorithm="sha256",
        digest="new",
        records=(first, second),
    )

    assert single.requires_inspection is False
    assert duplicate_new.requires_inspection is True
    assert duplicate_new.count == 2
    with pytest.raises(AttributeError):
        duplicate_new.digest = "different"  # type: ignore[misc]


def _ok_record(path: str, relative_path: str) -> FileHashRecord:
    return FileHashRecord(
        scan_id="incoming-scan",
        root_path="/incoming",
        path=path,
        relative_path=relative_path,
        size_bytes=12,
        mtime_ns=1779031234000000000,
        algorithm="sha256",
        digest="new",
        status="ok",
        error=None,
        scanned_at="2026-05-17T12:00:00Z",
    )
