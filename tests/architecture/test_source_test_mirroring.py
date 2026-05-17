from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

SOURCE_TO_TEST = {
    Path("dedup_scan/cli.py"): Path("tests/test_cli.py"),
    Path("dedup_scan/domain/records.py"): Path("tests/domain/test_records.py"),
    Path("dedup_scan/service/scanning.py"): Path("tests/service/test_scanning.py"),
    Path("dedup_scan/service/reporting.py"): Path("tests/service/test_reporting.py"),
    Path("dedup_scan/infrastructure/filesystem.py"): Path("tests/infrastructure/test_filesystem.py"),
    Path("dedup_scan/infrastructure/manifest_jsonl.py"): Path(
        "tests/infrastructure/test_manifest_jsonl.py"
    ),
    Path("dedup_scan/infrastructure/reporters.py"): Path("tests/infrastructure/test_reporters.py"),
}


def test_every_non_package_source_module_has_matching_test_module() -> None:
    source_modules = {
        path.relative_to(PROJECT_ROOT)
        for path in (PROJECT_ROOT / "dedup_scan").rglob("*.py")
        if path.name != "__init__.py"
    }

    assert source_modules == set(SOURCE_TO_TEST)
    for test_path in SOURCE_TO_TEST.values():
        assert (PROJECT_ROOT / test_path).exists()
