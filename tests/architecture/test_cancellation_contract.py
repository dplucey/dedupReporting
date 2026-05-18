import inspect

from dedup_scan import cli
from dedup_scan.infrastructure import manifest_jsonl
from dedup_scan.service import scanning, unique_compare


def test_public_io_entrypoints_accept_stop_signal() -> None:
    entrypoints = (
        scanning.scan_files,
        scanning.scan_files_parallel,
        scanning.hash_file,
        manifest_jsonl.write_manifest,
        manifest_jsonl.read_manifests,
        unique_compare.unique_to_target,
        cli.main,
    )

    for entrypoint in entrypoints:
        assert "stop_signal" in inspect.signature(entrypoint).parameters


def test_readme_documents_parallel_scan_cancellation_and_shutdown() -> None:
    with open("README.md", encoding="utf-8") as file_handle:
        readme = file_handle.read()

    assert "worker pool is scoped to each scan" in readme
    assert "Interrupted scans exit non-zero" in readme
    assert "final manifest path is not replaced" in readme


def test_readme_documents_unique_compare_cancellation_and_shutdown() -> None:
    with open("README.md", encoding="utf-8") as file_handle:
        readme = file_handle.read()

    assert "unique-to-target command checks for stop requests" in readme
    assert "does not open original paths listed in manifests" in readme
