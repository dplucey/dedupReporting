from dataclasses import dataclass

from dedup_scan.domain.records import FileHashRecord
from dedup_scan.service.unique_compare import unique_to_target


def test_incoming_records_absent_from_target_hashes_are_unique() -> None:
    incoming = (
        _ok_record(scan_id="incoming", path="/incoming/new.jpg", digest="new"),
        _ok_record(scan_id="incoming", path="/incoming/existing.jpg", digest="existing"),
    )
    target = (_ok_record(scan_id="target", path="/target/existing.jpg", digest="existing"),)

    report = unique_to_target(incoming_records=incoming, target_records=target)

    assert len(report.groups) == 1
    assert report.groups[0].algorithm == "sha256"
    assert report.groups[0].digest == "new"
    assert [record.path for record in report.groups[0].records] == ["/incoming/new.jpg"]


def test_preserves_duplicate_new_incoming_records_and_flags_inspection() -> None:
    incoming = (
        _ok_record(scan_id="incoming", path="/incoming/a.jpg", digest="new"),
        _ok_record(scan_id="incoming", path="/incoming/copy/a.jpg", digest="new"),
    )

    report = unique_to_target(incoming_records=incoming, target_records=())

    assert len(report.groups) == 1
    assert [record.path for record in report.groups[0].records] == [
        "/incoming/a.jpg",
        "/incoming/copy/a.jpg",
    ]
    assert report.groups[0].requires_inspection is True


def test_error_records_are_counted_as_skipped_and_not_unique_candidates() -> None:
    incoming = (
        _error_record(scan_id="incoming", path="/incoming/unreadable.jpg"),
        _ok_record(scan_id="incoming", path="/incoming/new.jpg", digest="new"),
    )
    target = (
        _error_record(scan_id="target", path="/target/unreadable.jpg"),
        _ok_record(scan_id="target", path="/target/existing.jpg", digest="existing"),
    )

    report = unique_to_target(incoming_records=incoming, target_records=target)

    assert [group.digest for group in report.groups] == ["new"]
    assert report.skipped.incoming_error_records == 1
    assert report.skipped.target_error_records == 1


def test_unique_compare_stops_when_stop_signal_is_set() -> None:
    stop_signal = ManualStopSignal()
    incoming = (
        _ok_record(scan_id="incoming", path="/incoming/a.jpg", digest="a"),
        _ok_record(scan_id="incoming", path="/incoming/b.jpg", digest="b"),
    )

    def stop_after_first_record(record_count: int) -> None:
        if record_count == 1:
            stop_signal.set()

    report = unique_to_target(
        incoming_records=incoming,
        target_records=(),
        stop_signal=stop_signal,
        after_incoming_record=stop_after_first_record,
    )

    assert [group.digest for group in report.groups] == ["a"]


def _ok_record(*, scan_id: str, path: str, digest: str) -> FileHashRecord:
    return FileHashRecord(
        scan_id=scan_id,
        root_path=f"/{scan_id}",
        path=path,
        relative_path=path.removeprefix(f"/{scan_id}/"),
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
        root_path=f"/{scan_id}",
        path=path,
        relative_path=path.removeprefix(f"/{scan_id}/"),
        size_bytes=None,
        mtime_ns=None,
        algorithm="sha256",
        digest=None,
        status="error",
        error="permission denied",
        scanned_at="2026-05-17T12:00:00Z",
    )


@dataclass
class ManualStopSignal:
    stopped: bool = False

    def set(self) -> None:
        self.stopped = True

    def is_set(self) -> bool:
        return self.stopped
