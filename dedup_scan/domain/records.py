from dataclasses import dataclass
from typing import Literal


FileHashStatus = Literal["ok", "error"]


@dataclass(frozen=True, slots=True)
class FileHashRecord:
    scan_id: str
    root_path: str
    path: str
    relative_path: str
    size_bytes: int | None
    mtime_ns: int | None
    algorithm: str
    digest: str | None
    status: FileHashStatus
    error: str | None
    scanned_at: str
    schema_version: int = 1
    record_type: str = "file_hash"

    def __post_init__(self) -> None:
        if self.status == "ok":
            self._validate_ok_record()
        elif self.status == "error":
            self._validate_error_record()
        else:
            raise ValueError(f"unsupported file hash status: {self.status}")

    def _validate_ok_record(self) -> None:
        if self.digest is None:
            raise ValueError("ok records require digest")
        if self.size_bytes is None:
            raise ValueError("ok records require size_bytes")
        if self.mtime_ns is None:
            raise ValueError("ok records require mtime_ns")
        if self.error is not None:
            raise ValueError("ok records must not include error")

    def _validate_error_record(self) -> None:
        if self.digest is not None:
            raise ValueError("error records must not include digest")
        if self.error is None:
            raise ValueError("error records require error")


@dataclass(frozen=True, slots=True)
class DuplicateGroup:
    algorithm: str
    digest: str
    records: tuple[FileHashRecord, ...]

    @property
    def count(self) -> int:
        return len(self.records)
