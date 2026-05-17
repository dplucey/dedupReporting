# Duplicate File Scan Backlog

Planned: 2026-05-17
Status: OPEN
Completed: (tbd)

## Problem

We need read-only tooling that can scan one or more directories, record each file's full path and content hash, and later report files with matching hashes across one or more scans. The important constraint is that duplicates may be discovered across different runs and different directory sets, so every scanned file must be hashed during the scan rather than only hashing same-size candidates from a single run.

This solves two related use cases:

- Immediate duplicate identification across a set of directories.
- Historical duplicate identification from previously captured flat-file manifests.

Prior art: Unix `shasum` / `sha256sum` provide per-file hashes but no grouping or historical manifest contract. `fdupes` / `jdupes` provide mature duplicate detection but include action-oriented workflows. This tool intentionally stays read-only and report-only.

## Approach

Build a stdlib-first CLI around append-only JSON Lines manifests. Scanning reads file metadata and file contents, writes manifest rows, and never mutates scanned files. Reporting reads manifests and groups records by `(algorithm, digest)` to identify duplicate-content groups.

Initial implementation should use Python stdlib only unless a later backlog item explicitly justifies a dependency.

Layers touched:

- Domain: immutable scan and duplicate-group records; pure grouping logic.
- Service: scan orchestration, hash computation workflow, manifest loading, duplicate report generation.
- Infrastructure: filesystem traversal, JSONL manifest reader/writer, CLI, text and JSON output.

Data classification:

- File paths and directory names are Internal metadata because they may reveal usernames, project names, customer names, or business context.
- File contents are read to compute hashes but are never stored.
- Hashes are Internal by default; they can still act as identifiers for known files.
- Restricted data must never be logged. Errors should include paths only when reporting local scan failures to the operator.

## Security Acceptance Criteria

- File contents are read only for hashing and are never stored, logged, or emitted in manifests or reports.
- File paths may appear in manifests and operator-facing reports, but stack traces and raw internal exceptions are never printed by default.
- Manifest parsing rejects malformed JSON, unsupported schema versions, missing required fields, and invalid status/digest combinations with path and line-number context.
- Reporting treats manifests as untrusted input and never opens, stats, deletes, moves, links, chmods, chowns, or rewrites original file paths from manifest rows.
- CLI output may include local path metadata needed by the operator, but must not include file contents or Restricted data values from file contents.
- Scan and report code paths make no mutation calls against any scanned path. The manifest writer may write and replace only the explicitly requested manifest output path.
- No outbound network calls are introduced.
- No external runtime dependencies are introduced without a separate security review trigger and backlog item.

Flat-file contract:

```json
{"schema_version":1,"record_type":"file_hash","scan_id":"2026-05-17T12-00-00Z","root_path":"/data/photos","path":"/data/photos/a.jpg","relative_path":"a.jpg","size_bytes":4123456,"mtime_ns":1779031234000000000,"algorithm":"sha256","digest":"abc123...","status":"ok","error":null,"scanned_at":"2026-05-17T12:00:00Z"}
```

Failure rows should preserve scan completeness without pretending a hash exists:

```json
{"schema_version":1,"record_type":"file_hash","scan_id":"2026-05-17T12-00-00Z","root_path":"/data/photos","path":"/data/photos/private.bin","relative_path":"private.bin","size_bytes":null,"mtime_ns":null,"algorithm":"sha256","digest":null,"status":"error","error":"permission denied","scanned_at":"2026-05-17T12:00:00Z"}
```

Default behavior:

- Hash every regular file.
- Use SHA-256.
- Do not follow symlinks.
- Report duplicate groups only.
- Never delete, move, hardlink, symlink, chmod, chown, or rewrite scanned files.
- Emit warnings for unreadable files and continue.
- Exit non-zero for invalid arguments or manifest write failures.
- Exit zero for successful scans/reports, even when no duplicates are found.

## Architecture Invariants

- Domain imports no filesystem, JSON, CLI, process, or clock APIs.
- Service orchestrates use cases but contains no filesystem-specific traversal code.
- Infrastructure adapters implement filesystem and manifest I/O.
- All commands are read-only with respect to scanned directories.
- Reporting consumes manifests only; it does not touch the original filesystem.
- Every non-package source module has a mirrored test module; package `__init__.py` files are exempt unless they contain behavior.
- No external dependency is added without a backlog item that rejects the stdlib alternative.
- Public APIs that may block or perform I/O accept a cooperative cancellation/stop signal or document why the language/runtime path cannot practically cancel that operation.
- Errors returned to callers preserve cause; CLI output does not include stack traces by default.

## Workstream 0: Project Skeleton and Manifest Contract

Files touched:

- `pyproject.toml`
- `dedup_scan/__init__.py`
- `dedup_scan/domain/__init__.py`
- `dedup_scan/domain/records.py`
- `tests/domain/test_records.py`
- `tests/architecture/test_import_boundaries.py`
- `tests/architecture/test_dependency_policy.py`

Depends on: Nothing

Status: Complete

Branch: `feat-workstream-0-project-skeleton`

- [x] ITEM-001: Define immutable domain records
  - Test first: `tests/domain/test_records.py::test_file_hash_record_requires_digest_for_ok_status` asserts valid and invalid status/hash combinations.
  - Implementation: Add frozen dataclasses for `FileHashRecord` and `DuplicateGroup`.
  - Refactor: None.

- [x] ITEM-002: Enforce initial import boundaries
  - Test first: `tests/architecture/test_import_boundaries.py::test_domain_does_not_import_outer_layers_or_io_modules` asserts domain modules do not import filesystem, JSON, CLI, or service/infrastructure modules.
  - Implementation: Add a small AST-based architecture test.
  - Refactor: None.

- [x] ITEM-003: Add package metadata without external dependencies
  - Test first: `tests/architecture/test_dependency_policy.py::test_project_has_no_runtime_dependencies` asserts no non-stdlib runtime dependencies are declared.
  - Implementation: Add minimal `pyproject.toml` with package metadata and test configuration.
  - Refactor: None.

## Workstream A: Filesystem Scan and Hash Service

Files touched:

- `dedup_scan/service/__init__.py`
- `dedup_scan/service/scanning.py`
- `dedup_scan/infrastructure/__init__.py`
- `dedup_scan/infrastructure/filesystem.py`
- `tests/service/test_scanning.py`
- `tests/infrastructure/test_filesystem.py`

Depends on: Workstream 0

Status: Complete

Branch: `feat-workstream-a-filesystem-scan`

- [x] ITEM-004: Scan regular files and hash every file
  - Test first: `tests/service/test_scanning.py::test_scan_hashes_every_regular_file_even_when_sizes_are_unique` creates unique-size files and asserts every regular file receives a SHA-256 digest.
  - Implementation: Add scan orchestration that walks supplied roots, hashes every regular file, and returns domain records.
  - Refactor: None.

- [x] ITEM-005: Skip symlinks by default
  - Test first: `tests/infrastructure/test_filesystem.py::test_walk_skips_symlinks_by_default` creates a symlink and asserts it is not yielded as a regular file.
  - Implementation: Add filesystem walker defaulting to no symlink following.
  - Refactor: None.

- [x] ITEM-006: Continue after unreadable file errors
  - Test first: `tests/service/test_scanning.py::test_scan_records_error_and_continues_after_unreadable_file` asserts one unreadable file yields an error record while other files still hash.
  - Implementation: Convert per-file stat/open failures into `status="error"` records.
  - Refactor: Extract small helpers only if scan orchestration exceeds 50 lines.

- [x] ITEM-019: Stop scanning before the next file when cancellation is requested
  - Test first: `tests/service/test_scanning.py::test_scan_stops_before_hashing_next_file_when_stop_signal_is_set` creates multiple files, sets a stop signal after the first file is processed, and asserts later files are not hashed.
  - Implementation: Add a cooperative stop signal to the scan service and check it before each file.
  - Refactor: None.

- [x] ITEM-020: Stop file hashing between chunks when cancellation is requested
  - Test first: `tests/service/test_scanning.py::test_hash_file_checks_stop_signal_between_chunks` hashes a file through a chunked reader that sets the stop signal after one chunk and asserts hashing stops before consuming the rest.
  - Implementation: Hash files in chunks, check the stop signal between chunks, and document that cancellation cannot interrupt an OS read already in progress.
  - Refactor: None.

## Workstream B: JSONL Manifest Reader and Writer

Files touched:

- `dedup_scan/infrastructure/manifest_jsonl.py`
- `tests/infrastructure/test_manifest_jsonl.py`

Depends on: Workstream 0

Status: Complete

Branch: `feat-workstream-b-manifest-jsonl`

- [x] ITEM-007: Write JSONL manifests atomically enough for local CLI use
  - Test first: `tests/infrastructure/test_manifest_jsonl.py::test_write_manifest_emits_one_json_object_per_record` asserts newline-delimited JSON rows and stable schema fields.
  - Implementation: Add manifest writer using a temporary file in the target directory followed by replace.
  - Refactor: None.

- [x] ITEM-008: Read multiple manifests as a stream
  - Test first: `tests/infrastructure/test_manifest_jsonl.py::test_read_manifests_streams_records_from_multiple_files` asserts records from multiple manifest files are yielded without loading the full files into memory.
  - Implementation: Add generator-based JSONL reader with schema/version validation.
  - Refactor: None.

- [x] ITEM-009: Reject malformed manifest rows loudly
  - Test first: `tests/infrastructure/test_manifest_jsonl.py::test_read_manifest_reports_line_number_for_malformed_json` asserts an invalid row reports path and line number.
  - Implementation: Wrap JSON decode and schema errors with manifest location context.
  - Refactor: None.

- [x] ITEM-021: Stop manifest reading between rows when cancellation is requested
  - Test first: `tests/infrastructure/test_manifest_jsonl.py::test_read_manifests_stops_between_rows_when_stop_signal_is_set` reads a multi-row manifest, sets the stop signal after one yielded record, and asserts no additional rows are yielded.
  - Implementation: Add cooperative stop-signal support to manifest readers and check it between JSONL rows.
  - Refactor: None.

- [x] ITEM-029: Stop manifest writing between records when cancellation is requested
  - Test first: `tests/infrastructure/test_manifest_jsonl.py::test_write_manifest_stops_between_records_when_stop_signal_is_set` writes multiple records through a writer that sets the stop signal after one record and asserts later records are not written.
  - Implementation: Add cooperative stop-signal support to manifest writing, check it before write start and between records, and document that cancellation cannot interrupt an OS write already in progress.
  - Refactor: None.

## Workstream C: Duplicate Grouping and Reporting

Files touched:

- `dedup_scan/service/reporting.py`
- `dedup_scan/infrastructure/reporters.py`
- `tests/service/test_reporting.py`
- `tests/infrastructure/test_reporters.py`

Depends on: Workstream 0, Workstream B

Status: Complete

Branch: `feat-workstream-c-reporting`

- [x] ITEM-010: Group duplicates across manifests
  - Test first: `tests/service/test_reporting.py::test_groups_duplicate_hashes_across_different_scan_ids` asserts matching digests from different manifests appear in one duplicate group.
  - Implementation: Add pure grouping by `(algorithm, digest)` for `status="ok"` records.
  - Refactor: None.

- [x] ITEM-011: Ignore error records and singleton hashes in duplicate reports
  - Test first: `tests/service/test_reporting.py::test_duplicate_report_ignores_error_records_and_singletons` asserts only groups with at least two successful file records are returned.
  - Implementation: Filter records before grouping and emit only groups with `count > 1`.
  - Refactor: None.

- [x] ITEM-012: Provide text and JSON reporters
  - Test first: `tests/infrastructure/test_reporters.py::test_text_report_lists_digest_then_full_paths` and `tests/infrastructure/test_reporters.py::test_json_report_is_machine_readable` assert stable output shapes.
  - Implementation: Add reporter functions for human-readable text and JSON.
  - Refactor: None.

## Workstream D: CLI Composition Root

Files touched:

- `pyproject.toml`
- `dedup_scan/cli.py`
- `tests/test_cli.py`

Depends on: Workstream A, Workstream B, Workstream C

Status: Complete

Branch: `feat-workstream-d-cli`

- [x] ITEM-013: Add scan command
  - Test first: `tests/test_cli.py::test_scan_command_writes_manifest_for_all_files` invokes the CLI against a temp directory and asserts manifest rows exist for every regular file.
  - Implementation: Add `dedup-scan scan ROOT... --manifest PATH` composition root wiring filesystem, scanner, hasher, and manifest writer.
  - Refactor: None.

- [x] ITEM-014: Add report command
  - Test first: `tests/test_cli.py::test_report_command_reads_multiple_manifests_and_prints_duplicates` invokes the CLI with two manifests and asserts cross-run duplicates are printed.
  - Implementation: Add `dedup-scan report MANIFEST... --format text|json`.
  - Refactor: None.

- [x] ITEM-015: Keep CLI stack traces out of normal error output
  - Test first: `tests/test_cli.py::test_cli_errors_are_generic_without_stack_traces` asserts malformed input exits non-zero and does not print traceback text.
  - Implementation: Add top-level CLI exception handling with concise error messages.
  - Refactor: None.

- [x] ITEM-022: Wire CLI interrupts into cooperative cancellation
  - Test first: `tests/test_cli.py::test_scan_command_wires_interrupt_signal_to_scan_service` invokes the scan command with an injected stop signal or simulated interrupt and asserts the command exits non-zero without traceback text.
  - Implementation: Wire CLI signal or interrupt handling into service-layer cancellation.
  - Refactor: None.

- [x] ITEM-030: Expose installed CLI command
  - Test first: `tests/test_cli.py::test_project_declares_dedup_scan_console_script` asserts `pyproject.toml` declares a `dedup-scan` console script pointing at the CLI entry point.
  - Implementation: Add the `dedup-scan` console script entry to package metadata.
  - Refactor: None.

## Workstream Z: Invariant Verification and Operational Notes

Files touched:

- `tests/architecture/test_read_only_behavior.py`
- `tests/architecture/test_import_boundaries.py`
- `tests/architecture/test_dependency_policy.py`
- `tests/architecture/test_quality_gate_documented.py`
- `tests/architecture/test_source_test_mirroring.py`
- `tests/architecture/test_reporting_boundaries.py`
- `tests/architecture/test_cancellation_contract.py`
- `tests/architecture/test_security_acceptance.py`
- `tests/test_readme_examples.py`
- `README.md`

Depends on: Workstream D

Status: Not Started

Branch: `(tbd)`

- [ ] ITEM-016: Verify scan commands do not mutate scanned directories
  - Test first: `tests/architecture/test_read_only_behavior.py::test_scan_preserves_file_content_mode_and_directory_entries` records file content, mode, and directory entries before scan and asserts they are unchanged afterward.
  - Implementation: Add invariant test around the public CLI or service entry point.
  - Refactor: None.

- [ ] ITEM-017: Document manifest contract and operating model
  - Test first: `tests/test_readme_examples.py::test_readme_scan_and_report_commands_match_cli_parser` asserts documented commands remain parseable.
  - Implementation: Add README usage, schema example, read-only guarantee, data classification note, and known limitations.
  - Refactor: None.

- [ ] ITEM-018: Run final quality gate
  - Test first: `tests/architecture/test_quality_gate_documented.py::test_readme_lists_local_quality_gate_commands` asserts the documented quality gate includes formatter, linter, type/correctness check, security scan placeholder, secret scan placeholder, and tests.
  - Implementation: Document the local quality gate commands available for this stdlib-first project.
  - Refactor: None.

- [ ] ITEM-023: Verify source and test tree stay mirrored
  - Test first: `tests/architecture/test_source_test_mirroring.py::test_every_non_package_source_module_has_matching_test_module` asserts every `dedup_scan/**/*.py` module except package `__init__.py` files has a predictable mirrored test file.
  - Implementation: Add an architecture test that maps source modules to test paths.
  - Refactor: None.

- [ ] ITEM-024: Verify reporting never touches scanned filesystem paths
  - Test first: `tests/architecture/test_reporting_boundaries.py::test_reporting_uses_manifest_records_without_filesystem_access` builds manifest records with nonexistent original paths and asserts report generation succeeds without stat or open calls.
  - Implementation: Add an architecture or service test proving report flow consumes manifests only.
  - Refactor: None.

- [ ] ITEM-025: Verify dependency policy remains stdlib-only
  - Test first: `tests/architecture/test_dependency_policy.py::test_project_remains_stdlib_only_after_all_workstreams` asserts runtime dependencies are still empty after CLI, reporting, and scanning modules are added.
  - Implementation: Extend dependency policy checks to cover the completed package metadata.
  - Refactor: None.

- [ ] ITEM-026: Verify service layer does not import infrastructure
  - Test first: `tests/architecture/test_import_boundaries.py::test_service_layer_does_not_import_infrastructure_adapters` asserts service modules do not import `dedup_scan.infrastructure`.
  - Implementation: Extend AST import-boundary checks.
  - Refactor: None.

- [ ] ITEM-027: Verify I/O APIs expose cooperative cancellation
  - Test first: `tests/architecture/test_cancellation_contract.py::test_public_io_entrypoints_accept_stop_signal` asserts scan, manifest read/write, and CLI composition paths expose or document cooperative cancellation.
  - Implementation: Add signature or docstring-level architecture checks for public I/O entry points.
  - Refactor: None.

- [ ] ITEM-028: Verify security acceptance criteria
  - Test first: `tests/architecture/test_security_acceptance.py::test_scan_and_report_security_acceptance_criteria_are_enforced` asserts no outbound network imports, no scanned-path mutation APIs in scan/report modules, no stack traces in CLI errors, and no file-content fields in manifest or report records.
  - Implementation: Add architecture checks and focused CLI/service tests for the documented security criteria, scoped so manifest writes are allowed only for the explicitly requested manifest output path.
  - Refactor: None.

## Dependency Map

```text
Workstream 0
    ├── Workstream A
    └── Workstream B
            └── Workstream C

Workstream D depends on A, B, C
Workstream Z depends on D
```

Parallel execution plan:

- Workstream 0 blocks all implementation because it defines the domain contract and architecture invariant tests.
- Workstream A and Workstream B can run concurrently after Workstream 0 because they touch disjoint files.
- Workstream C can start after Workstream B and Workstream 0; it does not require filesystem scanning from Workstream A.
- Workstream D composes the completed service and infrastructure pieces.
- Workstream Z is last and verifies no behavioral or architectural regression.

## Approval Gate

Status: APPROVED
Decision: Approved
- Cooperative cancellation is covered by service, infrastructure, CLI, and architecture verification tasks.
- Architecture invariants are enforced by Workstream Z ratchet tests.
- Security acceptance criteria are documented and verified, with scanned-path mutation explicitly prohibited.
