import json

from dedup_scan.domain.unique import UniqueContentReport


def render_unique_text_report(report: UniqueContentReport) -> str:
    lines: list[str] = []
    for group in report.groups:
        inspection = ", requires inspection" if group.requires_inspection else ""
        lines.append(f"{group.algorithm} {group.digest} ({group.count} files{inspection})")
        for record in group.records:
            lines.append(f"  {record.path}")
        lines.append("")
    lines.append(
        "skipped "
        f"incoming_error_records={report.skipped.incoming_error_records} "
        f"target_error_records={report.skipped.target_error_records}"
    )
    return "\n".join(lines)


def render_unique_json_report(report: UniqueContentReport) -> str:
    return json.dumps(
        {
            "unique_to_target": [
                {
                    "algorithm": group.algorithm,
                    "digest": group.digest,
                    "count": group.count,
                    "requires_inspection": group.requires_inspection,
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
                for group in report.groups
            ],
            "skipped": {
                "incoming_error_records": report.skipped.incoming_error_records,
                "target_error_records": report.skipped.target_error_records,
            },
        },
        sort_keys=False,
    )
