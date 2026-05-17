from collections.abc import Callable, Iterable, Iterator, Sequence
from hashlib import sha256
from pathlib import Path
from typing import Protocol

from dedup_scan.domain.records import FileHashRecord


DEFAULT_CHUNK_SIZE = 1024 * 1024


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
) -> list[FileHashRecord]:
    records: list[FileHashRecord] = []

    for path in walk_files(roots):
        if _is_stopped(stop_signal):
            break
        records.append(
            _scan_one_file(
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
        if after_record is not None:
            after_record(len(records))

    return records


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
