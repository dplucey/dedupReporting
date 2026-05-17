import json
from pathlib import Path

import pytest

from dedup_scan.domain.records import FileHashRecord
from dedup_scan.infrastructure.manifest_jsonl import (
    ManifestFormatError,
    read_manifests,
    write_manifest,
)


def test_write_manifest_emits_one_json_object_per_record(tmp_path: Path) -> None:
    manifest_path = tmp_path / "scan.jsonl"
    records = (
        _ok_record(path="/data/photos/a.jpg", relative_path="a.jpg", digest="abc123"),
        _error_record(path="/data/photos/private.bin", relative_path="private.bin"),
    )

    write_manifest(manifest_path, records)

    rows = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines()]
    assert rows == [
        {
            "schema_version": 1,
            "record_type": "file_hash",
            "scan_id": "scan-1",
            "root_path": "/data/photos",
            "path": "/data/photos/a.jpg",
            "relative_path": "a.jpg",
            "size_bytes": 12,
            "mtime_ns": 100,
            "algorithm": "sha256",
            "digest": "abc123",
            "status": "ok",
            "error": None,
            "scanned_at": "2026-05-17T12:00:00Z",
        },
        {
            "schema_version": 1,
            "record_type": "file_hash",
            "scan_id": "scan-1",
            "root_path": "/data/photos",
            "path": "/data/photos/private.bin",
            "relative_path": "private.bin",
            "size_bytes": None,
            "mtime_ns": None,
            "algorithm": "sha256",
            "digest": None,
            "status": "error",
            "error": "permission denied",
            "scanned_at": "2026-05-17T12:00:00Z",
        },
    ]


def test_read_manifests_streams_records_from_multiple_files(tmp_path: Path) -> None:
    first_path = tmp_path / "first.jsonl"
    second_path = tmp_path / "second.jsonl"
    write_manifest(first_path, (_ok_record(path="/data/a.txt", relative_path="a.txt", digest="aaa"),))
    write_manifest(second_path, (_ok_record(path="/data/b.txt", relative_path="b.txt", digest="bbb"),))

    records = read_manifests((first_path, second_path))

    first = next(records)
    assert first.path == "/data/a.txt"
    assert first.digest == "aaa"

    second = next(records)
    assert second.path == "/data/b.txt"
    assert second.digest == "bbb"

    with pytest.raises(StopIteration):
        next(records)


def test_read_manifest_reports_line_number_for_malformed_json(tmp_path: Path) -> None:
    manifest_path = tmp_path / "broken.jsonl"
    manifest_path.write_text("{}\nnot-json\n", encoding="utf-8")

    records = read_manifests((manifest_path,))
    with pytest.raises(ManifestFormatError) as exc_info:
        list(records)

    message = str(exc_info.value)
    assert str(manifest_path) in message
    assert "line 1" in message
    assert "missing required field: schema_version" in message


def test_read_manifests_stops_between_rows_when_stop_signal_is_set(tmp_path: Path) -> None:
    manifest_path = tmp_path / "scan.jsonl"
    stop_signal = ManualStopSignal()
    write_manifest(
        manifest_path,
        (
            _ok_record(path="/data/a.txt", relative_path="a.txt", digest="aaa"),
            _ok_record(path="/data/b.txt", relative_path="b.txt", digest="bbb"),
        ),
    )

    records = read_manifests((manifest_path,), stop_signal=stop_signal)
    first = next(records)
    stop_signal.set()

    assert first.path == "/data/a.txt"
    with pytest.raises(StopIteration):
        next(records)


def test_write_manifest_stops_between_records_when_stop_signal_is_set(tmp_path: Path) -> None:
    manifest_path = tmp_path / "scan.jsonl"
    stop_signal = ManualStopSignal()
    records = StopAfterFirstRecord(
        stop_signal,
        (
            _ok_record(path="/data/a.txt", relative_path="a.txt", digest="aaa"),
            _ok_record(path="/data/b.txt", relative_path="b.txt", digest="bbb"),
        ),
    )

    write_manifest(manifest_path, records, stop_signal=stop_signal)

    rows = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines()]
    assert [row["path"] for row in rows] == ["/data/a.txt"]


def _ok_record(*, path: str, relative_path: str, digest: str) -> FileHashRecord:
    return FileHashRecord(
        scan_id="scan-1",
        root_path="/data/photos",
        path=path,
        relative_path=relative_path,
        size_bytes=12,
        mtime_ns=100,
        algorithm="sha256",
        digest=digest,
        status="ok",
        error=None,
        scanned_at="2026-05-17T12:00:00Z",
    )


def _error_record(*, path: str, relative_path: str) -> FileHashRecord:
    return FileHashRecord(
        scan_id="scan-1",
        root_path="/data/photos",
        path=path,
        relative_path=relative_path,
        size_bytes=None,
        mtime_ns=None,
        algorithm="sha256",
        digest=None,
        status="error",
        error="permission denied",
        scanned_at="2026-05-17T12:00:00Z",
    )


class ManualStopSignal:
    def __init__(self) -> None:
        self._is_set = False

    def set(self) -> None:
        self._is_set = True

    def is_set(self) -> bool:
        return self._is_set


class StopAfterFirstRecord:
    def __init__(
        self,
        stop_signal: ManualStopSignal,
        records: tuple[FileHashRecord, ...],
    ) -> None:
        self._stop_signal = stop_signal
        self._records = records
        self._index = 0

    def __iter__(self) -> "StopAfterFirstRecord":
        return self

    def __next__(self) -> FileHashRecord:
        if self._index >= len(self._records):
            raise StopIteration
        record = self._records[self._index]
        self._index += 1
        if self._index == 1:
            self._stop_signal.set()
        return record
