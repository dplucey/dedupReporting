from collections.abc import Iterator, Sequence
from pathlib import Path


class FilesystemReader:
    def stat(self, path: Path) -> tuple[int, int]:
        metadata = path.stat()
        return metadata.st_size, metadata.st_mtime_ns

    def chunks(self, path: Path, chunk_size: int) -> Iterator[bytes]:
        with path.open("rb") as file_handle:
            while chunk := file_handle.read(chunk_size):
                yield chunk


def walk_regular_files(roots: Sequence[Path]) -> Iterator[Path]:
    for root in roots:
        if root.is_symlink():
            continue
        if root.is_file():
            yield root
            continue
        if root.is_dir():
            yield from _walk_directory(root)


def _walk_directory(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            continue
        if path.is_file():
            yield path
