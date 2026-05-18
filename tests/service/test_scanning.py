import hashlib
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from dedup_scan.service.scanning import StopRequested, hash_file, scan_files, scan_files_parallel


@dataclass(frozen=True)
class FakeFile:
    path: Path
    content: bytes
    mtime_ns: int = 100
    stat_error: OSError | None = None
    open_error: OSError | None = None


def test_scan_hashes_every_regular_file_even_when_sizes_are_unique() -> None:
    files = (
        FakeFile(path=Path("/root/a.txt"), content=b"a"),
        FakeFile(path=Path("/root/b.txt"), content=b"bb", mtime_ns=200),
        FakeFile(path=Path("/root/c.txt"), content=b"ccc", mtime_ns=300),
    )
    reader = MultiFileReader(files)

    records = list(
        scan_files(
            roots=(Path("/root"),),
            walk_files=lambda roots: (fake_file.path for fake_file in files),
            reader=reader,
            scan_id="scan-1",
            scanned_at="2026-05-17T12:00:00Z",
        )
    )

    assert [record.path for record in records] == [str(fake_file.path) for fake_file in files]
    assert [record.digest for record in records] == [
        hashlib.sha256(fake_file.content).hexdigest() for fake_file in files
    ]
    assert {record.status for record in records} == {"ok"}


def test_scan_yields_records_as_files_are_hashed() -> None:
    files = (
        FakeFile(path=Path("/root/a.txt"), content=b"a"),
        FakeFile(path=Path("/root/b.txt"), content=b"bb"),
    )
    reader = MultiFileReader(files)

    records = scan_files(
        roots=(Path("/root"),),
        walk_files=lambda roots: (fake_file.path for fake_file in files),
        reader=reader,
        scan_id="scan-1",
        scanned_at="2026-05-17T12:00:00Z",
    )

    first = next(records)

    assert first.path == "/root/a.txt"
    assert reader.chunked_paths == [Path("/root/a.txt")]


def test_scan_records_error_and_continues_after_unreadable_file() -> None:
    files = (
        FakeFile(path=Path("/root/a.txt"), content=b"a"),
        FakeFile(path=Path("/root/private.bin"), content=b"", open_error=PermissionError("denied")),
        FakeFile(path=Path("/root/c.txt"), content=b"ccc", mtime_ns=300),
    )
    reader = MultiFileReader(files)

    records = list(
        scan_files(
            roots=(Path("/root"),),
            walk_files=lambda roots: (fake_file.path for fake_file in files),
            reader=reader,
            scan_id="scan-1",
            scanned_at="2026-05-17T12:00:00Z",
        )
    )

    assert [record.status for record in records] == ["ok", "error", "ok"]
    assert records[1].path == "/root/private.bin"
    assert records[1].digest is None
    assert records[1].error == "denied"
    assert records[2].digest == hashlib.sha256(b"ccc").hexdigest()


def test_scan_stops_before_hashing_next_file_when_stop_signal_is_set() -> None:
    stop_signal = ManualStopSignal()
    files = (
        FakeFile(path=Path("/root/a.txt"), content=b"a"),
        FakeFile(path=Path("/root/b.txt"), content=b"bb"),
    )
    reader = MultiFileReader(files)

    def stop_after_first_record(record_count: int) -> None:
        if record_count == 1:
            stop_signal.set()

    records = list(
        scan_files(
            roots=(Path("/root"),),
            walk_files=lambda roots: (fake_file.path for fake_file in files),
            reader=reader,
            scan_id="scan-1",
            scanned_at="2026-05-17T12:00:00Z",
            stop_signal=stop_signal,
            after_record=stop_after_first_record,
        )
    )

    assert [record.path for record in records] == ["/root/a.txt"]


def test_hash_file_checks_stop_signal_between_chunks() -> None:
    stop_signal = ManualStopSignal()
    chunks = StopAfterFirstChunk(stop_signal)

    with pytest.raises(StopRequested):
        hash_file(chunks, stop_signal=stop_signal)

    assert chunks.chunks_read == 1


def test_parallel_scan_hashes_every_regular_file_once() -> None:
    files = (
        FakeFile(path=Path("/root/a.txt"), content=b"a"),
        FakeFile(path=Path("/root/b.txt"), content=b"bb"),
        FakeFile(path=Path("/root/c.txt"), content=b"ccc"),
    )
    reader = MultiFileReader(files)

    records = list(
        scan_files_parallel(
            roots=(Path("/root"),),
            walk_files=lambda roots: (fake_file.path for fake_file in files),
            reader=reader,
            scan_id="scan-1",
            scanned_at="2026-05-17T12:00:00Z",
            workers=2,
        )
    )

    assert {record.path for record in records} == {str(fake_file.path) for fake_file in files}
    assert sorted(reader.chunked_paths) == sorted(fake_file.path for fake_file in files)


def test_parallel_scan_rejects_worker_count_outside_supported_range() -> None:
    files = (FakeFile(path=Path("/root/a.txt"), content=b"a"),)
    reader = MultiFileReader(files)

    with pytest.raises(ValueError, match="workers must be between 1 and 32"):
        list(
            scan_files_parallel(
                roots=(Path("/root"),),
                walk_files=lambda roots: (fake_file.path for fake_file in files),
                reader=reader,
                scan_id="scan-1",
                scanned_at="2026-05-17T12:00:00Z",
                workers=0,
            )
        )

    with pytest.raises(ValueError, match="workers must be between 1 and 32"):
        list(
            scan_files_parallel(
                roots=(Path("/root"),),
                walk_files=lambda roots: (fake_file.path for fake_file in files),
                reader=reader,
                scan_id="scan-1",
                scanned_at="2026-05-17T12:00:00Z",
                workers=33,
            )
        )


def test_parallel_scan_stops_submitting_new_work_when_stop_signal_is_set() -> None:
    stop_signal = ManualStopSignal()
    files = (
        FakeFile(path=Path("/root/a.txt"), content=b"a"),
        FakeFile(path=Path("/root/b.txt"), content=b"bb"),
        FakeFile(path=Path("/root/c.txt"), content=b"ccc"),
    )
    yielded_paths: list[Path] = []
    reader = MultiFileReader(files)

    def walk_files(roots: tuple[Path, ...]) -> Iterator[Path]:
        for fake_file in files:
            yielded_paths.append(fake_file.path)
            yield fake_file.path

    def stop_after_first_record(record_count: int) -> None:
        if record_count == 1:
            stop_signal.set()

    records = list(
        scan_files_parallel(
            roots=(Path("/root"),),
            walk_files=walk_files,
            reader=reader,
            scan_id="scan-1",
            scanned_at="2026-05-17T12:00:00Z",
            workers=2,
            max_in_flight=1,
            stop_signal=stop_signal,
            after_record=stop_after_first_record,
        )
    )

    assert [record.path for record in records] == ["/root/a.txt"]
    assert yielded_paths == [Path("/root/a.txt")]


def test_parallel_scan_limits_in_flight_work() -> None:
    files = tuple(
        FakeFile(path=Path(f"/root/{index}.txt"), content=str(index).encode())
        for index in range(5)
    )
    reader = MultiFileReader(files)
    yielded_count = 0
    max_submitted_before_record = 0

    def walk_files(roots: tuple[Path, ...]) -> Iterator[Path]:
        nonlocal yielded_count, max_submitted_before_record
        for fake_file in files:
            yielded_count += 1
            max_submitted_before_record = max(max_submitted_before_record, yielded_count)
            yield fake_file.path

    records = []
    for record in scan_files_parallel(
        roots=(Path("/root"),),
        walk_files=walk_files,
        reader=reader,
        scan_id="scan-1",
        scanned_at="2026-05-17T12:00:00Z",
        workers=2,
        max_in_flight=2,
    ):
        records.append(record)
        break

    assert len(records) == 1
    assert max_submitted_before_record == 2


def test_parallel_scan_never_opens_more_files_than_workers() -> None:
    files = tuple(
        FakeFile(path=Path(f"/root/{index}.txt"), content=str(index).encode())
        for index in range(6)
    )
    reader = ConcurrentTrackingReader(files)

    records = list(
        scan_files_parallel(
            roots=(Path("/root"),),
            walk_files=lambda roots: (fake_file.path for fake_file in files),
            reader=reader,
            scan_id="scan-1",
            scanned_at="2026-05-17T12:00:00Z",
            workers=3,
            max_in_flight=6,
        )
    )

    assert len(records) == 6
    assert reader.max_concurrent_opens <= 3


def test_parallel_scan_records_worker_file_errors_and_continues() -> None:
    files = (
        FakeFile(path=Path("/root/a.txt"), content=b"a"),
        FakeFile(path=Path("/root/private.bin"), content=b"", open_error=PermissionError("denied")),
        FakeFile(path=Path("/root/c.txt"), content=b"ccc"),
    )
    reader = MultiFileReader(files)

    records = list(
        scan_files_parallel(
            roots=(Path("/root"),),
            walk_files=lambda roots: (fake_file.path for fake_file in files),
            reader=reader,
            scan_id="scan-1",
            scanned_at="2026-05-17T12:00:00Z",
            workers=2,
        )
    )

    records_by_path = {record.path: record for record in records}
    assert records_by_path["/root/private.bin"].status == "error"
    assert records_by_path["/root/private.bin"].error == "denied"
    assert records_by_path["/root/a.txt"].status == "ok"
    assert records_by_path["/root/c.txt"].status == "ok"


def test_parallel_scan_worker_pool_is_scoped_to_iterator_lifetime() -> None:
    files = tuple(
        FakeFile(path=Path(f"/root/{index}.txt"), content=str(index).encode())
        for index in range(4)
    )
    reader = MultiFileReader(files)
    records = scan_files_parallel(
        roots=(Path("/root"),),
        walk_files=lambda roots: (fake_file.path for fake_file in files),
        reader=reader,
        scan_id="scan-1",
        scanned_at="2026-05-17T12:00:00Z",
        workers=2,
        max_in_flight=2,
    )

    first = next(records)
    records.close()

    assert first.path.startswith("/root/")
    assert len(reader.chunked_paths) <= 2


class MultiFileReader:
    def __init__(self, fake_files: tuple[FakeFile, ...]) -> None:
        self._files = {fake_file.path: fake_file for fake_file in fake_files}
        self.chunked_paths: list[Path] = []

    def stat(self, path: Path) -> tuple[int, int]:
        fake_file = self._files[path]
        if fake_file.stat_error is not None:
            raise fake_file.stat_error
        return len(fake_file.content), fake_file.mtime_ns

    def chunks(self, path: Path, chunk_size: int) -> Iterator[bytes]:
        self.chunked_paths.append(path)
        fake_file = self._files[path]
        if fake_file.open_error is not None:
            raise fake_file.open_error
        for index in range(0, len(fake_file.content), chunk_size):
            yield fake_file.content[index : index + chunk_size]


class ManualStopSignal:
    def __init__(self) -> None:
        self._is_set = False

    def set(self) -> None:
        self._is_set = True

    def is_set(self) -> bool:
        return self._is_set


class StopAfterFirstChunk:
    def __init__(self, stop_signal: ManualStopSignal) -> None:
        self._stop_signal = stop_signal
        self.chunks_read = 0

    def __iter__(self) -> "StopAfterFirstChunk":
        return self

    def __next__(self) -> bytes:
        if self.chunks_read == 0:
            self.chunks_read += 1
            self._stop_signal.set()
            return b"first"
        self.chunks_read += 1
        return b"second"


class ConcurrentTrackingReader(MultiFileReader):
    def __init__(self, fake_files: tuple[FakeFile, ...]) -> None:
        super().__init__(fake_files)
        self._lock = threading.Lock()
        self._current_opens = 0
        self.max_concurrent_opens = 0

    def chunks(self, path: Path, chunk_size: int) -> Iterator[bytes]:
        with self._lock:
            self._current_opens += 1
            self.max_concurrent_opens = max(self.max_concurrent_opens, self._current_opens)
        try:
            yield from super().chunks(path, chunk_size)
        finally:
            with self._lock:
                self._current_opens -= 1
