# ECI Statistical Reports (staging)

Offline staging pipeline for ECI Statistical Report 33 (Constituency Wise Detailed Result).

## Scope

- Parse OLE `.xls` / OOXML `.xlsx` workbooks only (magic-byte detection).
- Stage rows into `eci_election_result_source_record`.
- **Never** create or mutate `Person`, `Candidacy`, or `ElectionResult`.
- Identity is read-only (`EXACT_LINKED` / `AMBIGUOUS` / `UNRESOLVED` / `CONFLICT`).
- Do not invent `WON`/`LOST` or rank when the source lacks those columns.

## CLI

```bash
python -m collectors.eci.statistical_reports.cli import-fixture PATH [--dry-run]
```

Or:

```bash
python collectors/eci/statistical_reports/cli.py PATH [--dry-run]
```

## Fixture

`tests/fixtures/eci/statistical_reports/report33/report33_schema_fixture.xls`

Original live workbook capture was blocked by WAF (`BLOCKED_WAF_APPTRANA_406`). Schema labels match the published Report 33 PDF; row values are fictionalized.

## Versions

| Constant | Value |
|----------|-------|
| `COLLECTOR_NAME` | `eci_statistical_reports` |
| `COLLECTOR_VERSION` | `ECI_STAT_REPORT_COLLECTOR_V1` |
| `PARSER_VERSION` | `ECI_LS2024_REPORT33_PARSER_V1` |
