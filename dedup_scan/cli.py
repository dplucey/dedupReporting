import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Protocol

from dedup_scan.infrastructure.filesystem import FilesystemReader, walk_regular_files
from dedup_scan.infrastructure.manifest_jsonl import read_manifests, write_manifest
from dedup_scan.infrastructure.reporters import render_json_report, render_text_report
from dedup_scan.infrastructure.unique_reporters import (
    render_unique_json_report,
    render_unique_text_report,
)
from dedup_scan.service.reporting import duplicate_groups
from dedup_scan.service.scanning import MAX_SCAN_WORKERS, StopRequested, scan_files, scan_files_parallel
from dedup_scan.service.unique_compare import unique_to_target


PROGRESS_EVERY_RECORDS = 1000


class StopSignal(Protocol):
    def is_set(self) -> bool: ...


def main(
    argv: list[str] | None = None,
    *,
    stop_signal: StopSignal | None = None,
) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
        if args.command == "scan":
            return _scan_command(args, stop_signal=stop_signal)
        if args.command == "report":
            return _report_command(args, stop_signal=stop_signal)
        if args.command == "unique-to-target":
            return _unique_to_target_command(args, stop_signal=stop_signal)
        parser.error("missing command")
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 1
    except StopRequested as exc:
        print(f"error: stopped: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dedup-scan")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan")
    scan_parser.add_argument("roots", nargs="+", type=Path)
    scan_parser.add_argument("--manifest", required=True, type=Path)
    scan_parser.add_argument("--workers", type=int, default=1)

    report_parser = subparsers.add_parser("report")
    report_parser.add_argument("manifests", nargs="+", type=Path)
    report_parser.add_argument("--format", choices=("text", "json"), default="text")

    unique_parser = subparsers.add_parser("unique-to-target")
    unique_parser.add_argument("manifests", nargs="+", type=Path)
    unique_parser.add_argument("--against", required=True, type=Path)
    unique_parser.add_argument("--format", choices=("text", "json"), default="text")

    return parser


def _scan_command(args: argparse.Namespace, *, stop_signal: StopSignal | None) -> int:
    if stop_signal is not None and stop_signal.is_set():
        raise StopRequested("scan stopped before start")

    _validate_manifest_outside_roots(args.manifest, tuple(args.roots))
    _validate_workers(args.workers)
    scanned_at = _utc_timestamp()
    scan_kwargs = {
        "roots": tuple(args.roots),
        "walk_files": walk_regular_files,
        "reader": FilesystemReader(),
        "scan_id": _scan_id(scanned_at),
        "scanned_at": scanned_at,
        "stop_signal": stop_signal,
        "after_record": _progress_reporter(),
    }
    if args.workers == 1:
        records = scan_files(**scan_kwargs)
    else:
        records = scan_files_parallel(**scan_kwargs, workers=args.workers)
    if stop_signal is not None and stop_signal.is_set():
        raise StopRequested("scan stopped")
    write_manifest(args.manifest, _stop_checked_records(records, stop_signal), stop_signal=stop_signal)
    return 0


def _stop_checked_records(records, stop_signal: StopSignal | None):
    for record in records:
        if stop_signal is not None and stop_signal.is_set():
            raise StopRequested("scan stopped")
        yield record
        if stop_signal is not None and stop_signal.is_set():
            raise StopRequested("scan stopped")


def _validate_workers(workers: int) -> None:
    if workers < 1 or workers > MAX_SCAN_WORKERS:
        raise ValueError(f"workers must be between 1 and {MAX_SCAN_WORKERS}")


def _progress_reporter() -> Callable[[int], None]:
    def report(record_count: int) -> None:
        if record_count % PROGRESS_EVERY_RECORDS == 0:
            print(f"scanned={record_count}", file=sys.stderr)

    return report


def _validate_manifest_outside_roots(manifest_path: Path, roots: tuple[Path, ...]) -> None:
    resolved_manifest = manifest_path.resolve(strict=False)
    for root in roots:
        resolved_root = root.resolve(strict=False)
        if resolved_manifest == resolved_root or resolved_root in resolved_manifest.parents:
            raise ValueError("manifest path must be outside scan roots")


def _report_command(args: argparse.Namespace, *, stop_signal: StopSignal | None) -> int:
    groups = duplicate_groups(read_manifests(tuple(args.manifests), stop_signal=stop_signal))
    if args.format == "json":
        print(render_json_report(groups))
    else:
        report = render_text_report(groups)
        if report:
            print(report)
    return 0


def _unique_to_target_command(args: argparse.Namespace, *, stop_signal: StopSignal | None) -> int:
    if stop_signal is not None and stop_signal.is_set():
        raise StopRequested("unique-to-target stopped before start")

    report = unique_to_target(
        incoming_records=read_manifests(tuple(args.manifests), stop_signal=stop_signal),
        target_records=read_manifests((args.against,), stop_signal=stop_signal),
        stop_signal=stop_signal,
    )
    if stop_signal is not None and stop_signal.is_set():
        raise StopRequested("unique-to-target stopped")
    if args.format == "json":
        print(render_unique_json_report(report))
    else:
        rendered = render_unique_text_report(report)
        if rendered:
            print(rendered)
    return 0


def _utc_timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _scan_id(scanned_at: str) -> str:
    return scanned_at.replace(":", "-")


if __name__ == "__main__":
    raise SystemExit(main())
