# ECI Statistical Reports

Staging-first ingestion for ECI Statistical Report workbooks (starting with Report 33).

## Design principles

1. **Staging only** — rows land in `eci_election_result_source_record`. The pipeline does **not** create or mutate `Person`, `Candidacy`, or `ElectionResult`.
2. **No canary allowlist expansion** — this path does not call the live ECI results portal and does not widen the live-results canary allowlist. See [eci-live-results.md](eci-live-results.md).
3. **Immutable archive** — payloads go through `archive_raw` / `build_raw_from_bytes` with full provenance (`collector_name`, `parser_version`, `extraction_method=archived_workbook`, `extraction_confidence=NULL`).
4. **SOURCE_CHANGED** — same logical URL with a different SHA creates a **new** `SourceDocument` and a `ReviewItem`; prior staging rows are retained (not replaced).
5. **Identity is read-only** — exact normalized name + election year + type + constituency may set `identity_candidacy_id` (`EXACT_LINKED`). Ambiguous / missing / party conflict → `AMBIGUOUS` / `UNRESOLVED` / `CONFLICT`. Never auto-create identity entities.

## Report 33

See [eci-statistical-report-33-schema.md](eci-statistical-report-33-schema.md).

## Future: Result-at-a-Glance

Constituency “Result-at-a-Glance” pages (or HTML summaries) may become a **secondary** evidence stream later. They are out of scope for this staging milestone and must not be treated as a substitute for Report 33 detailed rows.

## CLI

```bash
python -m collectors.eci.statistical_reports.cli import-fixture PATH [--dry-run]
```

Offline fixtures only — no ECI network calls.
