from dataclasses import dataclass

from dedup_scan.domain.records import FileHashRecord


@dataclass(frozen=True, slots=True)
class UniqueContentGroup:
    algorithm: str
    digest: str
    records: tuple[FileHashRecord, ...]

    @property
    def count(self) -> int:
        return len(self.records)

    @property
    def requires_inspection(self) -> bool:
        return self.count > 1


@dataclass(frozen=True, slots=True)
class SkippedRecordCounts:
    incoming_error_records: int = 0
    target_error_records: int = 0


@dataclass(frozen=True, slots=True)
class UniqueContentReport:
    groups: tuple[UniqueContentGroup, ...]
    skipped: SkippedRecordCounts
