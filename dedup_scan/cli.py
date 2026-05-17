import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from dedup_scan.infrastructure.filesystem import FilesystemReader, walk_regular_files
from dedup_scan.infrastructure.manifest_jsonl import read_manifests, write_manifest
from dedup_scan.infrastructure.reporters import render_json_report, render_text_report
from dedup_scan.service.reporting import duplicate_groups
from dedup_scan.service.scanning import StopRequested, scan_files


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
        parser.error("missing command")
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

    report_parser = subparsers.add_parser("report")
    report_parser.add_argument("manifests", nargs="+", type=Path)
    report_parser.add_argument("--format", choices=("text", "json"), default="text")

    return parser


def _scan_command(args: argparse.Namespace, *, stop_signal: StopSignal | None) -> int:
    if stop_signal is not None and stop_signal.is_set():
        raise StopRequested("scan stopped before start")

    scanned_at = _utc_timestamp()
    records = scan_files(
        roots=tuple(args.roots),
        walk_files=walk_regular_files,
        reader=FilesystemReader(),
        scan_id=_scan_id(scanned_at),
        scanned_at=scanned_at,
        stop_signal=stop_signal,
    )
    if stop_signal is not None and stop_signal.is_set():
        raise StopRequested("scan stopped")
    write_manifest(args.manifest, records, stop_signal=stop_signal)
    return 0


def _report_command(args: argparse.Namespace, *, stop_signal: StopSignal | None) -> int:
    groups = duplicate_groups(read_manifests(tuple(args.manifests), stop_signal=stop_signal))
    if args.format == "json":
        print(render_json_report(groups))
    else:
        report = render_text_report(groups)
        if report:
            print(report)
    return 0


def _utc_timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _scan_id(scanned_at: str) -> str:
    return scanned_at.replace(":", "-")


if __name__ == "__main__":
    raise SystemExit(main())
