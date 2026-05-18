import tomllib
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_project_has_no_runtime_dependencies() -> None:
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())
    project = pyproject["project"]

    assert project.get("dependencies", []) == []


def test_project_remains_stdlib_only_after_unique_compare() -> None:
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())
    project = pyproject["project"]

    assert project.get("dependencies", []) == []
    assert project["scripts"] == {"dedup-scan": "dedup_scan.cli:main"}
