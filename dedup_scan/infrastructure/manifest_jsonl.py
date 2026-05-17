import json
import os
import tempfile
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any, Protocol

from dedup_scan.domain.records import FileHashRecord


class StopSignal(Protocol):
    def is_set(self) -> bool: ...


class ManifestFormatError(ValueError):
    pass


REQUIRED_FIELDS = (
    "schema_version",
    "record_type",
    "scan_id",
    "root_path",
    "path",
    "relative_path",
    "size_bytes",
    "mtime_ns",
    "algorithm",
    "digest",
    "status",
    "error",
    "scanned_at",
)


def write_manifest(
    manifest_path: Path,
    records: Iterable[FileHashRecord],
    *,
    stop_signal: StopSignal | None = None,
) -> None:
    if _is_stopped(stop_signal):
        return
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = _temporary_path(manifest_path)

    try:
        with temp_path.open("w", encoding="utf-8") as file_handle:
            for record in records:
                file_handle.write(json.dumps(_record_to_row(record), sort_keys=False))
                file_handle.write("\n")
                if _is_stopped(stop_signal):
                    break
        os.replace(temp_path, manifest_path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def read_manifests(
    manifest_paths: Sequence[Path],
    *,
    stop_signal: StopSignal | None = None,
) -> Iterator[FileHashRecord]:
    for manifest_path in manifest_paths:
        with manifest_path.open("r", encoding="utf-8") as file_handle:
            for line_number, line in enumerate(file_handle, start=1):
                if _is_stopped(stop_signal):
                    return
                yield _row_to_record(
                    _parse_json_line(manifest_path, line_number, line),
                    manifest_path,
                    line_number,
                )


def _record_to_row(record: FileHashRecord) -> dict[str, Any]:
    row = asdict(record)
    return {field: row[field] for field in REQUIRED_FIELDS}


def _row_to_record(
    row: Any,
    manifest_path: Path,
    line_number: int,
) -> FileHashRecord:
    if not isinstance(row, dict):
        raise _format_error(manifest_path, line_number, "row must be a JSON object")

    for field in REQUIRED_FIELDS:
        if field not in row:
            raise _format_error(manifest_path, line_number, f"missing required field: {field}")

    if row["schema_version"] != 1:
        raise _format_error(manifest_path, line_number, "unsupported schema_version")
    if row["record_type"] != "file_hash":
        raise _format_error(manifest_path, line_number, "unsupported record_type")

    try:
        return FileHashRecord(
            scan_id=row["scan_id"],
            root_path=row["root_path"],
            path=row["path"],
            relative_path=row["relative_path"],
            size_bytes=row["size_bytes"],
            mtime_ns=row["mtime_ns"],
            algorithm=row["algorithm"],
            digest=row["digest"],
            status=row["status"],
            error=row["error"],
            scanned_at=row["scanned_at"],
            schema_version=row["schema_version"],
            record_type=row["record_type"],
        )
    except ValueError as exc:
        raise _format_error(manifest_path, line_number, str(exc)) from exc


def _parse_json_line(manifest_path: Path, line_number: int, line: str) -> Any:
    try:
        return json.loads(line)
    except json.JSONDecodeError as exc:
        raise _format_error(manifest_path, line_number, "malformed JSON") from exc


def _format_error(manifest_path: Path, line_number: int, message: str) -> ManifestFormatError:
    return ManifestFormatError(f"{manifest_path}: line {line_number}: {message}")


def _temporary_path(manifest_path: Path) -> Path:
    file_descriptor, raw_path = tempfile.mkstemp(
        prefix=f".{manifest_path.name}.",
        suffix=".tmp",
        dir=manifest_path.parent,
    )
    os.close(file_descriptor)
    return Path(raw_path)


def _is_stopped(stop_signal: StopSignal | None) -> bool:
    return stop_signal is not None and stop_signal.is_set()
