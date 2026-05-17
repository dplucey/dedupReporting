import inspect

from dedup_scan import cli
from dedup_scan.infrastructure import manifest_jsonl
from dedup_scan.service import scanning


def test_public_io_entrypoints_accept_stop_signal() -> None:
    entrypoints = (
        scanning.scan_files,
        scanning.hash_file,
        manifest_jsonl.write_manifest,
        manifest_jsonl.read_manifests,
        cli.main,
    )

    for entrypoint in entrypoints:
        assert "stop_signal" in inspect.signature(entrypoint).parameters
