# Collectors

## Pipeline

```text
fetch → archive_raw (immutable) → parse → normalize → validate → persist + provenance
```

## Deduplication

When `archive_raw` sees a payload whose SHA-256 already exists under the same `source_name`:

1. The original payload bytes are **never overwritten**.
2. A new observation directory is created with `metadata.json`.
3. Metadata sets `deduplicated: true` and `reused_payload_from` to the existing payload path (or a local symlink).

## Git provenance

`get_git_commit_sha()` returns HEAD, `MPTA_GIT_COMMIT_SHA`, or `UNKNOWN`. Ingestion never fails solely because Git is missing. Optional `git_dirty` is stored separately on `collector_run`.

## Failure artifacts

Failures write `data/failures/COLLECTOR_FAILURE_*.json` with stage, exception type, message, and git commit (no secrets).

## External identifiers

See [identity-resolution.md](identity-resolution.md). External ECI IDs map through `candidacy_source_identifier` to a candidacy — never to `person.person_id`.

## Live ECI results canary

See [eci-live-results.md](eci-live-results.md). Live networking is **off** unless `MPTA_ECI_LIVE_ENABLED=true` and `--confirm-live` are both set. CI remains fully offline (MockTransport).

## ECI statistical-report capture

See [eci-statistical-report-acquisition.md](eci-statistical-report-acquisition.md). Manual `workflow_dispatch` only; gated by `MPTA_ECI_STAT_REPORT_LIVE_ENABLED` + `--confirm-live`. Capture archives exact bytes and does not mutate canonical Person/Candidacy/ElectionResult rows.
