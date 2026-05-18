from collections import defaultdict
from collections.abc import Callable, Iterable
from typing import Protocol

from dedup_scan.domain.records import FileHashRecord
from dedup_scan.domain.unique import SkippedRecordCounts, UniqueContentGroup, UniqueContentReport


class StopSignal(Protocol):
    def is_set(self) -> bool: ...


def unique_to_target(
    *,
    incoming_records: Iterable[FileHashRecord],
    target_records: Iterable[FileHashRecord],
    stop_signal: StopSignal | None = None,
    after_incoming_record: Callable[[int], None] | None = None,
) -> UniqueContentReport:
    target_hashes: set[tuple[str, str]] = set()
    target_error_records = 0

    for record in target_records:
        if _is_stopped(stop_signal):
            break
        if record.status == "error":
            target_error_records += 1
            continue
        if record.digest is not None:
            target_hashes.add((record.algorithm, record.digest))

    grouped: dict[tuple[str, str], list[FileHashRecord]] = defaultdict(list)
    incoming_error_records = 0
    incoming_count = 0

    for record in incoming_records:
        if _is_stopped(stop_signal):
            break
        if record.status == "error":
            incoming_error_records += 1
        elif record.digest is not None:
            key = (record.algorithm, record.digest)
            if key not in target_hashes:
                grouped[key].append(record)
        incoming_count += 1
        if after_incoming_record is not None:
            after_incoming_record(incoming_count)

    return UniqueContentReport(
        groups=tuple(
            UniqueContentGroup(algorithm=algorithm, digest=digest, records=tuple(records))
            for (algorithm, digest), records in grouped.items()
        ),
        skipped=SkippedRecordCounts(
            incoming_error_records=incoming_error_records,
            target_error_records=target_error_records,
        ),
    )


def _is_stopped(stop_signal: StopSignal | None) -> bool:
    return stop_signal is not None and stop_signal.is_set()
