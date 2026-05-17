import json
from collections.abc import Iterable

from dedup_scan.domain.records import DuplicateGroup


def render_text_report(groups: Iterable[DuplicateGroup]) -> str:
    lines: list[str] = []
    for group in groups:
        lines.append(f"{group.algorithm} {group.digest} ({group.count} files)")
        for record in group.records:
            lines.append(f"  {record.path}")
        lines.append("")
    return "\n".join(lines)


def render_json_report(groups: Iterable[DuplicateGroup]) -> str:
    return json.dumps(
        {
            "duplicate_groups": [
                {
                    "algorithm": group.algorithm,
                    "digest": group.digest,
                    "count": group.count,
                    "files": [
                        {
                            "scan_id": record.scan_id,
                            "root_path": record.root_path,
                            "path": record.path,
                            "relative_path": record.relative_path,
                            "size_bytes": record.size_bytes,
                            "mtime_ns": record.mtime_ns,
                        }
                        for record in group.records
                    ],
                }
                for group in groups
            ]
        },
        sort_keys=False,
    )
