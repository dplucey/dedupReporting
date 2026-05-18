# dedupReporting

Read-only duplicate file scan reporting tools.

`dedup-scan` scans regular files, records file path metadata and SHA-256 content hashes in JSON Lines manifests, and reports duplicate-content groups from one or more manifests. Scans are report-only: they do not delete, move, link, chmod, chown, or rewrite scanned files.

## Local Usage

From a checkout, run the CLI module with the project venv:

```bash
$ .venv/bin/python -m dedup_scan.cli scan /data/photos --manifest manifests/photos.jsonl
$ .venv/bin/python -m dedup_scan.cli report manifests/photos.jsonl manifests/archive.jsonl --format text
$ .venv/bin/python -m dedup_scan.cli report manifests/photos.jsonl --format json
```

Serial scan is the default. Parallel hashing is opt-in:

```bash
$ .venv/bin/python -m dedup_scan.cli scan /data/photos --manifest manifests/photos.jsonl --workers 1
$ .venv/bin/python -m dedup_scan.cli scan /data/photos --manifest manifests/photos.jsonl --workers 2
```

## Installed Usage

After installing the package, the console command is `dedup-scan`:

```bash
$ .venv/bin/python -m pip install -e .
$ dedup-scan scan /data/photos --manifest manifests/photos.jsonl
$ dedup-scan report manifests/photos.jsonl manifests/archive.jsonl --format text
$ dedup-scan report manifests/photos.jsonl --format json
```


Default behavior:

- Hash every regular file with SHA-256.
- Do not follow symlinks.
- Require `--manifest` to be outside every scanned root.
- Use `--workers 1` by default, preserving serial traversal and output order.
- Use `--workers 2` through `--workers 32` to opt into parallel hashing; output order is unspecified when workers exceed 1.
- Continue after unreadable files by writing `status: "error"` rows.
- Stream scan records to a temporary manifest while scanning, then atomically replace the final manifest path on success.
- Print scan progress to stderr every 1000 processed records.
- Report duplicate groups only.
- Return zero for successful scans and reports, including reports with no duplicates.
- Return non-zero for invalid arguments, invalid manifests, interrupted scans, or manifest write failures.

## Manifest Contract

Manifests are JSON Lines files. Each line is one `file_hash` record.

Successful file row:

```json
{"schema_version":1,"record_type":"file_hash","scan_id":"2026-05-17T12-00-00Z","root_path":"/data/photos","path":"/data/photos/a.jpg","relative_path":"a.jpg","size_bytes":4123456,"mtime_ns":1779031234000000000,"algorithm":"sha256","digest":"abc123...","status":"ok","error":null,"scanned_at":"2026-05-17T12:00:00Z"}
```

Unreadable file row:

```json
{"schema_version":1,"record_type":"file_hash","scan_id":"2026-05-17T12-00-00Z","root_path":"/data/photos","path":"/data/photos/private.bin","relative_path":"private.bin","size_bytes":null,"mtime_ns":null,"algorithm":"sha256","digest":null,"status":"error","error":"permission denied","scanned_at":"2026-05-17T12:00:00Z"}
```

Manifest readers reject malformed JSON, unsupported schema versions, missing required fields, and invalid status/digest combinations with manifest path and line-number context.

## Data Classification

File paths, directory names, hashes, sizes, mtimes, and scan IDs are Internal metadata. File contents are read only to compute hashes; contents are never stored in manifests, reports, or logs.

## Operating Model

Reporting consumes manifests only. It does not open, stat, delete, move, link, chmod, chown, or rewrite original paths listed in manifests.

Cancellation is cooperative. Scan traversal checks for stop requests before each file. Hashing checks between chunks and cannot interrupt an OS read already in progress. Manifest reading and writing check between rows/records and cannot interrupt an OS read or write already in progress. A hidden temporary manifest is created in the target manifest directory during scans and is replaced into the final path only after a successful scan.

For parallel scans, the worker pool is scoped to each scan and is shut down before the command exits. Interrupted scans exit non-zero, stop submitting new work, drain or cancel in-flight work through the scoped worker pool, and the final manifest path is not replaced.

Known limitations:

- SHA-256 is the only supported digest algorithm.
- Manifests contain full local paths and should be handled as Internal metadata.
- Parallel scans can improve throughput on SSDs and some network filesystems, but may reduce performance on spinning disks or saturated mounts. Use `--workers 1` for lowest impact and deterministic traversal order.
- No persistent database or cross-host coordination is included.

## Local Quality Gate

Run:

```bash
.venv/bin/python -m pytest
```

Current stdlib-first placeholders:

- formatter: pending stdlib-first project decision
- linter: pending stdlib-first project decision
- type/correctness check: pending stdlib-first project decision
- security scan placeholder: add a language-idiomatic SAST command when security tooling is selected
- secret scan placeholder: add a repository secret scan command when security tooling is selected
