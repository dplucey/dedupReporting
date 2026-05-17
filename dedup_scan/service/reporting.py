from collections import defaultdict
from collections.abc import Iterable

from dedup_scan.domain.records import DuplicateGroup, FileHashRecord


def duplicate_groups(records: Iterable[FileHashRecord]) -> list[DuplicateGroup]:
    grouped: dict[tuple[str, str], list[FileHashRecord]] = defaultdict(list)

    for record in records:
        if record.status != "ok" or record.digest is None:
            continue
        grouped[(record.algorithm, record.digest)].append(record)

    return [
        DuplicateGroup(algorithm=algorithm, digest=digest, records=tuple(group_records))
        for (algorithm, digest), group_records in grouped.items()
        if len(group_records) > 1
    ]
