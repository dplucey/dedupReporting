from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from collections.abc import Callable, Iterable, Iterator, Sequence
from hashlib import sha256
from pathlib import Path
from typing import Protocol

from dedup_scan.domain.records import FileHashRecord


DEFAULT_CHUNK_SIZE = 1024 * 1024
MAX_SCAN_WORKERS = 32


class StopRequested(Exception):
    """Raised when cooperative cancellation stops an in-progress operation."""


class StopSignal(Protocol):
    def is_set(self) -> bool: ...


class FileReader(Protocol):
    def stat(self, path: Path) -> tuple[int, int]: ...

    def chunks(self, path: Path, chunk_size: int) -> Iterator[bytes]: ...


def scan_files(
    *,
    roots: Sequence[Path],
    walk_files: Callable[[Sequence[Path]], Iterable[Path]],
    reader: FileReader,
    scan_id: str,
    scanned_at: str,
    algorithm: str = "sha256",
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    stop_signal: StopSignal | None = None,
    after_record: Callable[[int], None] | None = None,
) -> Iterator[FileHashRecord]:
    record_count = 0

    for path in walk_files(roots):
        if _is_stopped(stop_signal):
            break
        yield _scan_one_file(
            path=path,
            roots=roots,
            reader=reader,
            scan_id=scan_id,
            scanned_at=scanned_at,
            algorithm=algorithm,
            chunk_size=chunk_size,
            stop_signal=stop_signal,
        )
        record_count += 1
        if after_record is not None:
            after_record(record_count)


def scan_files_parallel(
    *,
    roots: Sequence[Path],
    walk_files: Callable[[Sequence[Path]], Iterable[Path]],
    reader: FileReader,
    scan_id: str,
    scanned_at: str,
    workers: int,
    max_in_flight: int | None = None,
    algorithm: str = "sha256",
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    stop_signal: StopSignal | None = None,
    after_record: Callable[[int], None] | None = None,
) -> Iterator[FileHashRecord]:
    if workers < 1 or workers > MAX_SCAN_WORKERS:
        raise ValueError(f"workers must be between 1 and {MAX_SCAN_WORKERS}")
    if workers == 1:
        yield from scan_files(
            roots=roots,
            walk_files=walk_files,
            reader=reader,
            scan_id=scan_id,
            scanned_at=scanned_at,
            algorithm=algorithm,
            chunk_size=chunk_size,
            stop_signal=stop_signal,
            after_record=after_record,
        )
        return

    in_flight_limit = max_in_flight if max_in_flight is not None else workers * 4
    if in_flight_limit < 1:
        raise ValueError("max_in_flight must be at least 1")

    # Ownership: this generator owns task submission and executor shutdown.
    # Worker threads read/hash one path each; the caller consumes result records
    # and remains the only manifest writer.
    path_iterator = iter(walk_files(roots))
    pending: set[Future[FileHashRecord]] = set()
    record_count = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        _submit_until_full(
            pending=pending,
            executor=executor,
            path_iterator=path_iterator,
            in_flight_limit=in_flight_limit,
            roots=roots,
            reader=reader,
            scan_id=scan_id,
            scanned_at=scanned_at,
            algorithm=algorithm,
            chunk_size=chunk_size,
            stop_signal=stop_signal,
        )

        while pending:
            completed, pending = wait(pending, return_when=FIRST_COMPLETED)
            for future in completed:
                yield future.result()
                record_count += 1
                if after_record is not None:
                    after_record(record_count)

            _submit_until_full(
                pending=pending,
                executor=executor,
                path_iterator=path_iterator,
                in_flight_limit=in_flight_limit,
                roots=roots,
                reader=reader,
                scan_id=scan_id,
                scanned_at=scanned_at,
                algorithm=algorithm,
                chunk_size=chunk_size,
                stop_signal=stop_signal,
            )


def hash_file(
    chunks: Iterable[bytes],
    *,
    stop_signal: StopSignal | None = None,
) -> str:
    digest = sha256()
    for chunk in chunks:
        digest.update(chunk)
        _raise_if_stopped(stop_signal)
    return digest.hexdigest()


def _submit_until_full(
    *,
    pending: set[Future[FileHashRecord]],
    executor: ThreadPoolExecutor,
    path_iterator: Iterator[Path],
    in_flight_limit: int,
    roots: Sequence[Path],
    reader: FileReader,
    scan_id: str,
    scanned_at: str,
    algorithm: str,
    chunk_size: int,
    stop_signal: StopSignal | None,
) -> None:
    while len(pending) < in_flight_limit and not _is_stopped(stop_signal):
        try:
            path = next(path_iterator)
        except StopIteration:
            return
        if _is_stopped(stop_signal):
            return
        pending.add(
            executor.submit(
                _scan_one_file,
                path=path,
                roots=roots,
                reader=reader,
                scan_id=scan_id,
                scanned_at=scanned_at,
                algorithm=algorithm,
                chunk_size=chunk_size,
                stop_signal=stop_signal,
            )
        )


def _scan_one_file(
    *,
    path: Path,
    roots: Sequence[Path],
    reader: FileReader,
    scan_id: str,
    scanned_at: str,
    algorithm: str,
    chunk_size: int,
    stop_signal: StopSignal | None,
) -> FileHashRecord:
    try:
        size_bytes, mtime_ns = reader.stat(path)
        digest = hash_file(reader.chunks(path, chunk_size), stop_signal=stop_signal)
    except StopRequested:
        raise
    except OSError as exc:
        return _error_record(
            path=path,
            roots=roots,
            scan_id=scan_id,
            scanned_at=scanned_at,
            algorithm=algorithm,
            error=str(exc),
        )

    return FileHashRecord(
        scan_id=scan_id,
        root_path=str(_root_for(path, roots)),
        path=str(path),
        relative_path=str(_relative_path(path, roots)),
        size_bytes=size_bytes,
        mtime_ns=mtime_ns,
        algorithm=algorithm,
        digest=digest,
        status="ok",
        error=None,
        scanned_at=scanned_at,
    )


def _error_record(
    *,
    path: Path,
    roots: Sequence[Path],
    scan_id: str,
    scanned_at: str,
    algorithm: str,
    error: str,
) -> FileHashRecord:
    return FileHashRecord(
        scan_id=scan_id,
        root_path=str(_root_for(path, roots)),
        path=str(path),
        relative_path=str(_relative_path(path, roots)),
        size_bytes=None,
        mtime_ns=None,
        algorithm=algorithm,
        digest=None,
        status="error",
        error=error,
        scanned_at=scanned_at,
    )


def _root_for(path: Path, roots: Sequence[Path]) -> Path:
    for root in roots:
        try:
            path.relative_to(root)
        except ValueError:
            continue
        return root
    return path.parent


def _relative_path(path: Path, roots: Sequence[Path]) -> Path:
    root = _root_for(path, roots)
    try:
        return path.relative_to(root)
    except ValueError:
        return path.name


def _raise_if_stopped(stop_signal: StopSignal | None) -> None:
    if _is_stopped(stop_signal):
        raise StopRequested("operation stopped by stop signal")


def _is_stopped(stop_signal: StopSignal | None) -> bool:
    return stop_signal is not None and stop_signal.is_set()
