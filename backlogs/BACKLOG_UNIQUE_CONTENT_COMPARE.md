# Unique Content Compare Backlog

Planned: 2026-05-17
Status: OPEN
Completed: (tbd)

## Problem

We need read-only tooling that compares an incoming manifest against a target manifest and identifies incoming files whose content does not already exist in the target. This supports ingest planning: operators can decide which files from a new directory should be added to a target directory without mutating either directory during analysis.

The comparison must preserve incoming multiplicity. If multiple incoming paths share the same new digest that is absent from the target, every incoming path is reported. Those duplicate-new groups require later operator inspection because adding every path may or may not be desired.

Prior art: `rsync --checksum` can identify transfer candidates but is action-oriented and path-based by default. `comm` / `sort` over `sha256sum` output can compare hashes but does not preserve the manifest schema, scan context, or inspection flags. This feature stays report-only and manifest-driven.

## Approach

Add a read-only comparison/reporting path over existing JSONL manifests. The scanner remains unchanged. Operators first scan target and incoming directories, then run a compare command over the manifests:

```bash
dedup-scan unique manifests/incoming.jsonl --against manifests/target.jsonl --format text
```

Definition:

- **Unique-to-target file**: an incoming `status="ok"` file record whose `(algorithm, digest)` is absent from all target `status="ok"` records.
- **Multiplicity preserved**: every matching incoming path is listed, even when multiple incoming paths share the same unique digest.
- **Requires inspection**: a unique-to-target digest with more than one incoming file record. The report flags these duplicate-new groups so the operator can decide whether to add all paths or one representative later.
- Incoming and target `status="error"` rows do not participate in hash-set membership. They are excluded from add candidates and counted as skipped input.

Initial implementation should use Python stdlib only. No new dependencies are justified.

Layers touched:

- Domain: immutable unique-content group/report records; pure comparison logic.
- Service: manifest comparison orchestration over record streams.
- Infrastructure: text/JSON unique report rendering and CLI command wiring.

Data classification:

- Same as scan manifests: file paths, directory names, hashes, sizes, mtimes, and scan IDs are Internal metadata.
- File contents are never read during comparison and are never emitted.
- Reports may include incoming paths needed by the operator, but not file contents.

## Security Acceptance Criteria

- Compare/reporting consumes manifest records only. It never opens, stats, deletes, moves, links, chmods, chowns, or rewrites original incoming or target paths listed in manifests.
- Error records are excluded from uniqueness decisions and cannot cause a file to be listed as safe to add.
- CLI output must not include stack traces by default.
- No outbound network calls are introduced.
- No external runtime dependencies are introduced.
- JSON output is machine-readable and does not include file-content fields.

Output shape:

```json
{
  "unique_to_target": [
    {
      "algorithm": "sha256",
      "digest": "abc123",
      "count": 1,
      "requires_inspection": false,
      "files": [
        {
          "scan_id": "incoming-scan",
          "root_path": "/incoming",
          "path": "/incoming/photo1.jpg",
          "relative_path": "photo1.jpg",
          "size_bytes": 123,
          "mtime_ns": 1779031234000000000
        }
      ]
    }
  ],
  "skipped": {
    "incoming_error_records": 0,
    "target_error_records": 0
  }
}
```

Default behavior:

- Preserve multiplicity.
- Flag duplicate-new groups with `requires_inspection: true`.
- Report unique-to-target groups only.
- Do not read original filesystem paths from manifests.
- Exit zero for successful comparisons, even when no unique files are found.
- Exit non-zero for invalid arguments or invalid manifests.

## Architecture Invariants

- Domain imports no filesystem, JSON, CLI, process, or clock APIs.
- Service orchestrates comparison but imports no infrastructure adapters.
- Infrastructure adapters implement CLI and report formatting.
- Compare/reporting consumes manifests only; it does not touch original filesystem paths.
- Every non-package source module has a mirrored test module.
- No external dependency is added.
- Public APIs that may block or perform I/O accept a cooperative cancellation/stop signal or document why cancellation is not practical for that path.
- Errors returned to callers preserve cause; CLI output does not include stack traces by default.

## Workstream 0: Domain Compare Contract

Files touched:

- `dedup_scan/domain/unique.py`
- `tests/domain/test_unique.py`
- `tests/architecture/test_source_test_mirroring.py`

Depends on: Nothing

Status: Not Started

Branch: `(tbd)`

- [ ] ITEM-031: Define immutable unique-content report records
  - Test first: `tests/domain/test_unique.py::test_unique_content_group_flags_duplicate_new_records_for_inspection` asserts `requires_inspection` is false for one file and true for multiple files.
  - Implementation: Add frozen dataclasses for `UniqueContentGroup`, `SkippedRecordCounts`, and `UniqueContentReport`.
  - Refactor: None.

- [ ] ITEM-032: Extend source/test mirroring for unique domain module
  - Test first: `tests/architecture/test_source_test_mirroring.py::test_every_non_package_source_module_has_matching_test_module` expects `dedup_scan/domain/unique.py` to map to `tests/domain/test_unique.py`.
  - Implementation: Extend the existing mirroring map.
  - Refactor: None.

## Workstream A: Pure Unique Comparison Service

Files touched:

- `dedup_scan/service/unique_compare.py`
- `tests/service/test_unique_compare.py`
- `tests/architecture/test_source_test_mirroring.py`
- `tests/architecture/test_import_boundaries.py`

Depends on: Workstream 0

Status: Not Started

Branch: `(tbd)`

- [ ] ITEM-033: Identify incoming records absent from target hashes
  - Test first: `tests/service/test_unique_compare.py::test_incoming_records_absent_from_target_hashes_are_unique` asserts incoming ok records absent from target are returned as unique groups.
  - Implementation: Add pure comparison by `(algorithm, digest)` over incoming and target records.
  - Refactor: None.

- [ ] ITEM-034: Preserve incoming multiplicity and flag inspection groups
  - Test first: `tests/service/test_unique_compare.py::test_preserves_duplicate_new_incoming_records_and_flags_inspection` asserts two incoming files with the same new digest are both listed in one group with `requires_inspection=True`.
  - Implementation: Group unique incoming records by `(algorithm, digest)` without dropping duplicate incoming paths.
  - Refactor: None.

- [ ] ITEM-035: Exclude error records from uniqueness decisions
  - Test first: `tests/service/test_unique_compare.py::test_error_records_are_counted_as_skipped_and_not_unique_candidates` asserts incoming and target error rows are counted but never used as candidates or blockers.
  - Implementation: Track skipped incoming and target error counts on the report.
  - Refactor: None.

- [ ] ITEM-036: Enforce service boundary for unique compare
  - Test first: `tests/architecture/test_import_boundaries.py::test_service_layer_does_not_import_infrastructure_adapters` asserts `dedup_scan.service.unique_compare` imports no infrastructure modules.
  - Implementation: Extend existing architecture test coverage naturally through module discovery.
  - Refactor: None.

## Workstream B: Unique Reporters

Files touched:

- `dedup_scan/infrastructure/unique_reporters.py`
- `tests/infrastructure/test_unique_reporters.py`
- `tests/architecture/test_source_test_mirroring.py`

Depends on: Workstream 0, Workstream A

Status: Not Started

Branch: `(tbd)`

- [ ] ITEM-037: Render text unique report with inspection flags
  - Test first: `tests/infrastructure/test_unique_reporters.py::test_text_unique_report_marks_duplicate_new_groups_for_inspection` asserts text output lists digest, count, paths, and an inspection marker for duplicate-new groups.
  - Implementation: Add text renderer for `UniqueContentReport`.
  - Refactor: None.

- [ ] ITEM-038: Render JSON unique report
  - Test first: `tests/infrastructure/test_unique_reporters.py::test_json_unique_report_is_machine_readable` asserts the documented JSON output shape including `requires_inspection` and skipped counts.
  - Implementation: Add JSON renderer for `UniqueContentReport`.
  - Refactor: None.

## Workstream C: CLI Unique Command

Files touched:

- `dedup_scan/cli.py`
- `tests/test_cli.py`
- `README.md`

Depends on: Workstream A, Workstream B

Status: Not Started

Branch: `(tbd)`

- [ ] ITEM-039: Add unique command
  - Test first: `tests/test_cli.py::test_unique_command_compares_incoming_manifest_against_target_manifest` invokes `dedup-scan unique INCOMING --against TARGET --format text` and asserts unique incoming paths are printed while target-existing hashes are omitted.
  - Implementation: Wire manifest readers, unique comparison service, and text/JSON reporters into the CLI composition root.
  - Refactor: None.

- [ ] ITEM-040: Keep unique command errors generic
  - Test first: `tests/test_cli.py::test_unique_command_errors_are_generic_without_stack_traces` invokes the unique command with an invalid manifest and asserts non-zero exit without traceback text.
  - Implementation: Reuse existing top-level CLI exception handling.
  - Refactor: None.

- [ ] ITEM-041: Document unique compare workflow
  - Test first: `tests/test_readme_examples.py::test_readme_scan_report_and_unique_commands_match_cli_parser` asserts README scan/report/unique examples parse with the CLI parser.
  - Implementation: Add README usage, output semantics, multiplicity-preserved note, and inspection warning.
  - Refactor: None.

## Workstream Z: Final Invariant Verification

Files touched:

- `tests/architecture/test_reporting_boundaries.py`
- `tests/architecture/test_security_acceptance.py`
- `tests/architecture/test_dependency_policy.py`
- `tests/architecture/test_cancellation_contract.py`
- `tests/architecture/test_source_test_mirroring.py`
- `README.md`

Depends on: Workstream C

Status: Not Started

Branch: `(tbd)`

- [ ] ITEM-042: Verify unique compare never touches manifest paths
  - Test first: `tests/architecture/test_reporting_boundaries.py::test_unique_compare_uses_manifest_records_without_filesystem_access` builds incoming and target records with nonexistent original paths and asserts comparison/report rendering succeeds without stat or open calls.
  - Implementation: Add boundary test for unique comparison path.
  - Refactor: None.

- [ ] ITEM-043: Verify security acceptance for unique compare
  - Test first: `tests/architecture/test_security_acceptance.py::test_unique_compare_security_acceptance_criteria_are_enforced` asserts no outbound network imports, no original-path mutation APIs, no file-content fields in JSON output, and no stack traces in CLI errors.
  - Implementation: Extend existing security acceptance checks for unique modules.
  - Refactor: None.

- [ ] ITEM-044: Verify dependency and cancellation policies remain intact
  - Test first: `tests/architecture/test_dependency_policy.py::test_project_remains_stdlib_only_after_unique_compare` and `tests/architecture/test_cancellation_contract.py::test_public_io_entrypoints_accept_stop_signal` assert no runtime dependencies and unique CLI/manifest paths preserve cancellation contracts.
  - Implementation: Extend existing policy tests.
  - Refactor: None.

## Dependency Map

```text
Workstream 0
    └── Workstream A
            └── Workstream B
                    └── Workstream C
                            └── Workstream Z
```

Parallel execution plan:

- Workstream 0 defines the domain output contract and blocks comparison/reporting work.
- Workstream A depends on the domain report records.
- Workstream B depends on A because reporters render the final report shape.
- Workstream C depends on A and B because the CLI composes manifest reading, comparison, and rendering.
- Workstream Z runs last and verifies architecture/security invariants after all modules exist.

## Approval Gate

Status: CHANGES_REQUESTED
Decision: Changes required
- Unique-to-target semantics preserve incoming multiplicity.
- Duplicate-new groups are explicitly flagged for operator inspection.
- Feature remains report-only; no copy/move/apply behavior is included.

Approve this architecture plan to proceed with implementation?
