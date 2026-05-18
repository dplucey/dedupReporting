# Parallel Scan Backlog

Planned: 2026-05-17
Status: OPEN
Completed: (tbd)

## Problem

Large scans currently hash files serially. That preserves correctness but underuses multi-core systems and can make scans over SSDs, network filesystems, or mixed-size directory trees take much longer than necessary.

We need configurable parallel hashing that improves throughput without weakening data integrity. The scanner must remain read-only with respect to scanned directories, and manifest output must remain single-writer and atomically replaced only after a successful scan.

Prior art: `find | xargs -P sha256sum` and tools like `fd`/`ripgrep` use bounded worker parallelism for filesystem-heavy workloads, but they do not preserve this project’s manifest schema, error-row semantics, cancellation contract, or single-writer manifest invariant. This feature adopts the proven producer/worker/single-writer pattern while keeping domain/service boundaries intact.

## Approach

Add configurable parallel hashing to `dedup-scan scan`.

Pipeline:

```text
filesystem walk -> bounded in-flight work -> hash workers -> single manifest writer
```

Concurrency model:

- Walker remains a single producer over scan roots.
- Hash workers stat/open/read/hash individual files and return exactly one `FileHashRecord` per path.
- Manifest writing remains single-threaded through the existing JSONL writer.
- Output order is not guaranteed when `--workers > 1`.
- Default worker count is **1**, preserving serial streaming and current output-order behavior by default.
- CLI exposes `--workers N`; values above 1 opt into parallel hashing for speed.
- Bounded in-flight work prevents submitting the entire directory tree to the executor. Default `max_in_flight = workers * 4`.
- CLI worker count is capped at 32 to bound descriptor pressure and resource consumption.

Rationale for threads:

- File hashing is I/O-heavy and `hashlib` can release the GIL for larger chunks.
- Threads avoid process-pickling records and simplify cancellation/error handling.
- Multiprocessing is not justified until profiling proves CPU-bound hashing dominates.

Layers touched:

- Service: parallel scan orchestration, bounded task submission, worker cancellation behavior.
- Infrastructure: no new filesystem mutation APIs; existing filesystem adapter remains the path reader.
- CLI: `--workers`, validation, documentation.

Data classification:

- No change. Paths, hashes, sizes, mtimes, and scan IDs remain Internal metadata.
- File contents are read only for hashing and never emitted.

## Security Acceptance Criteria

- Parallel scan is read-only with respect to scanned directories.
- Manifest writing remains single-threaded.
- Every yielded path produces at most one manifest row.
- Per-file stat/open/read failures become `status="error"` records and do not stop unrelated worker tasks.
- Maximum concurrently open scan files is bounded by `workers`.
- CLI rejects `--workers` values outside `1..32`.
- No outbound network calls are introduced.
- No external runtime dependencies are introduced.
- Shared mutable state is avoided or synchronized through standard library concurrency primitives.
- Cancellation is cooperative: walker stops submitting new work, workers check cancellation between chunks, and in-flight work drains without leaked workers.
- After cancellation is observed, scan exits non-zero and the final manifest path is not replaced. A temporary manifest may remain for operator inspection or cleanup.
- Any concurrency primitives declare ownership in code comments or tests: who submits, who consumes, and who shuts down.

Default behavior:

- `dedup-scan scan` uses `--workers 1` unless overridden.
- `--workers 1` preserves serial streaming behavior and current directory traversal order.
- `--workers N` rejects values below 1 or above 32.
- Parallel output order is unspecified when `N > 1`.
- Manifest temp file is line-buffered and replaced into the final path only after scan completion.

## Architecture Invariants

- Domain imports no concurrency, filesystem, JSON, CLI, process, or clock APIs.
- Service imports no infrastructure adapters.
- Manifest writer has one caller thread writing rows.
- Scanned directories are never mutated.
- Parallel scan worker count is bounded to protect file descriptors and storage backends.
- Interrupted scans do not replace the final manifest path.
- Every non-package source module has a mirrored test module.
- No external dependency is added.
- Public APIs that may block or perform I/O accept a cooperative cancellation/stop signal or document the boundary.
- Thread pools are scoped and shut down deterministically.

## Workstream 0: Parallel Scan Contract

Files touched:

- `dedup_scan/service/scanning.py`
- `tests/service/test_scanning.py`
- `tests/architecture/test_cancellation_contract.py`

Depends on: Nothing

Status: Complete

Branch: `feat-parallel-scan-contract`

- [x] ITEM-045: Add parallel scan API with serial-compatible output contract
  - Test first: `tests/service/test_scanning.py::test_parallel_scan_hashes_every_regular_file_once` asserts each walked path produces exactly one `FileHashRecord`.
  - Implementation: Add `scan_files_parallel(..., workers: int, max_in_flight: int | None = None)` returning an iterator of records.
  - Refactor: Extract shared single-file scan helper only as needed.

- [x] ITEM-046: Reject invalid worker counts
  - Test first: `tests/service/test_scanning.py::test_parallel_scan_rejects_worker_count_outside_supported_range` asserts workers below 1 and above 32 raise `ValueError`.
  - Implementation: Validate `1 <= workers <= 32` at the service boundary.
  - Refactor: None.

- [x] ITEM-047: Preserve cancellation contract in parallel scan
  - Test first: `tests/service/test_scanning.py::test_parallel_scan_stops_submitting_new_work_when_stop_signal_is_set` asserts no new paths are submitted after cancellation and already-started workers drain without deadlock.
  - Implementation: Check stop signal before submission and between completed futures; workers reuse chunk-level cancellation from `hash_file`.
  - Refactor: None.

## Workstream A: Bounded Worker Execution

Files touched:

- `dedup_scan/service/scanning.py`
- `tests/service/test_scanning.py`

Depends on: Workstream 0

Status: Complete

Branch: `feat-parallel-scan-contract`

- [x] ITEM-048: Bound in-flight hash work
  - Test first: `tests/service/test_scanning.py::test_parallel_scan_limits_in_flight_work` uses a controlled fake reader and asserts submitted-but-unconsumed work never exceeds `max_in_flight`.
  - Implementation: Use `ThreadPoolExecutor` with bounded submit/drain logic, defaulting `max_in_flight` to `workers * 4`.
  - Refactor: None.

- [x] ITEM-057: Bound concurrent file opens by worker count
  - Test first: `tests/service/test_scanning.py::test_parallel_scan_never_opens_more_files_than_workers` uses a blocking fake reader and asserts concurrent opens do not exceed the configured worker count.
  - Implementation: Ensure each worker handles one file at a time and no extra reader threads are introduced.
  - Refactor: None.

- [x] ITEM-049: Convert per-file worker errors into error records
  - Test first: `tests/service/test_scanning.py::test_parallel_scan_records_worker_file_errors_and_continues` asserts one unreadable file yields an error record while other files still hash.
  - Implementation: Ensure worker execution uses existing `_scan_one_file` error-row behavior.
  - Refactor: None.

- [x] ITEM-050: Document concurrency ownership in service code
  - Test first: `tests/service/test_scanning.py::test_parallel_scan_worker_pool_is_scoped_to_iterator_lifetime` asserts the iterator can be partially consumed and closed without leaked executor work.
  - Implementation: Scope executor lifetime inside the generator and document producer/worker/result ownership near the parallel orchestration.
  - Refactor: None.

## Workstream B: CLI Worker Configuration

Files touched:

- `dedup_scan/cli.py`
- `tests/test_cli.py`
- `README.md`

Depends on: Workstream A

Status: Complete

Branch: `feat-parallel-scan-contract`

- [x] ITEM-051: Add scan workers option with serial default
  - Test first: `tests/test_cli.py::test_scan_command_defaults_to_one_worker` asserts scan uses the serial scan path unless `--workers` is set above 1.
  - Implementation: Add `--workers` to the scan command with default `1`; route `workers == 1` to serial `scan_files`, otherwise to `scan_files_parallel`.
  - Refactor: None.

- [x] ITEM-052: Validate CLI workers value
  - Test first: `tests/test_cli.py::test_scan_command_rejects_workers_outside_supported_range_without_traceback` invokes `--workers 0` and `--workers 33` and asserts non-zero exit without traceback text.
  - Implementation: Validate worker count at CLI or service boundary and reuse generic error handling.
  - Refactor: None.

- [x] ITEM-053: Document parallel scan tuning
  - Test first: `tests/test_readme_examples.py::test_readme_scan_commands_with_workers_match_cli_parser` asserts README examples with `--workers 1` and `--workers 2` parse.
  - Implementation: Document default `--workers 1`, opt-in `--workers 2+`, output order caveat, SSD/HDD/network tuning guidance, and single-writer manifest guarantee.
  - Refactor: None.

## Workstream Z: Final Concurrency Invariants

Files touched:

- `tests/architecture/test_security_acceptance.py`
- `tests/architecture/test_cancellation_contract.py`
- `tests/architecture/test_import_boundaries.py`
- `tests/architecture/test_source_test_mirroring.py`
- `README.md`

Depends on: Workstream B

Status: Not Started

Branch: `(tbd)`

- [ ] ITEM-054: Verify manifest writer remains single-threaded
  - Test first: `tests/architecture/test_security_acceptance.py::test_parallel_scan_preserves_single_manifest_writer_invariant` asserts parallel service does not import or call manifest writing and CLI still calls one writer with an iterator.
  - Implementation: Add architecture check over service/CLI imports and call shape.
  - Refactor: None.

- [ ] ITEM-058: Verify interrupted parallel scans do not replace final manifest
  - Test first: `tests/architecture/test_security_acceptance.py::test_interrupted_parallel_scan_does_not_replace_final_manifest` asserts a cancelled parallel scan exits non-zero and leaves the final manifest path absent or unchanged.
  - Implementation: Ensure CLI finalization treats cancellation as failure and relies on manifest writer cleanup/final replace rules.
  - Refactor: None.

- [ ] ITEM-055: Verify no dependency or boundary regressions
  - Test first: `tests/architecture/test_import_boundaries.py::test_service_layer_does_not_import_infrastructure_adapters` and `tests/architecture/test_source_test_mirroring.py::test_every_non_package_source_module_has_matching_test_module` remain green with parallel scan.
  - Implementation: Extend existing invariant data only if new modules are added.
  - Refactor: None.

- [ ] ITEM-056: Verify cancellation and shutdown documentation
  - Test first: `tests/architecture/test_cancellation_contract.py::test_public_io_entrypoints_accept_stop_signal` plus README assertions verify parallel scan cancellation/shutdown behavior is documented.
  - Implementation: Extend README and architecture tests for worker ownership, stop signal, and executor shutdown.
  - Refactor: None.

## Dependency Map

```text
Workstream 0
    └── Workstream A
            └── Workstream B
                    └── Workstream Z
```

Parallel execution plan:

- Workstream 0 defines the public service contract and cancellation behavior.
- Workstream A depends on 0 because it implements bounded executor orchestration.
- Workstream B depends on A because CLI routing must call the completed service behavior.
- Workstream Z runs last because it verifies the final concurrency/security invariants.

## Approval Gate

Status: APPROVED
Decision: Approved
- Default worker count is 1 and configurable with `--workers`.
- Worker count is capped at 32.
- Manifest writing remains single-threaded.
- Parallelism is bounded to avoid unbounded memory growth.
- Concurrent open scan files are bounded by worker count.
- Interrupted scans do not replace the final manifest path.
- Thread pool ownership, cancellation, and shutdown are explicit acceptance criteria.
