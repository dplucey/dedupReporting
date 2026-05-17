from pathlib import Path


def test_readme_lists_local_quality_gate_commands() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")

    expected_fragments = (
        ".venv/bin/python -m pytest",
        "formatter: pending stdlib-first project decision",
        "linter: pending stdlib-first project decision",
        "type/correctness check: pending stdlib-first project decision",
        "security scan placeholder",
        "secret scan placeholder",
    )

    for fragment in expected_fragments:
        assert fragment in readme
