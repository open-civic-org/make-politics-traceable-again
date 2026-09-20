# ECI statistical-report acquisition (manual GitHub Action)

## Purpose

Authorized maintainers can capture **one** official ECI statistical-report workbook via a
manual GitHub Actions workflow. Capture is **acquisition only**:

```text
manual workflow_dispatch
  → validate URL / host allowlist
  → guarded HTTPS download (exact bytes)
  → immutable raw archive + SHA-256 + metadata
  → upload GitHub Actions artifact
```

No Person / Candidacy / ElectionResult mutation occurs in this workflow.

Parser / staging / canonical reconciliation remain separate (offline-testable) layers.

## Operator steps

1. GitHub → **Actions**
2. Select **ECI Statistical Report Capture**
3. **Run workflow**
4. Enter:
   - official HTTPS ECI report URL (required; no default)
   - report number (e.g. `33`)
   - report title (e.g. `Constituency Wise Detailed Result`)
   - election year (default `2024`)
   - election type (default `LOK_SABHA`)
5. Run
6. Download the uploaded artifact (payload + `metadata.json` + `capture_report.json`)

## CLI (same gates as the Action)

```bash
MPTA_ECI_STAT_REPORT_LIVE_ENABLED=true \
uv run python -m collectors.eci.statistical_reports.cli capture \
  --url "https://www.eci.gov.in/.../33-....xls" \
  --report-number 33 \
  --report-title "Constituency Wise Detailed Result" \
  --election-year 2024 \
  --election-type LOK_SABHA \
  --confirm-live
```

Both `MPTA_ECI_STAT_REPORT_LIVE_ENABLED=true` and `--confirm-live` are required.
Default for the env flag is **false**. Normal CI never sets it.

## Host allowlist

Hostname equality only (parsed host):

```text
www.eci.gov.in
eci.gov.in
```

Rejected: `http://`, IP literals, localhost/private IPs, userinfo URLs, non-allowlisted hosts
(including `results.eci.gov.in` — that portal remains the Milestone 4 canary only).

Redirects: `follow_redirects=false`; each `Location` is validated before the next request.

## Limits

```text
MAX_REPORTS_PER_RUN = 1
MAX_HTTP_ATTEMPTS = 5
MIN_REQUEST_INTERVAL_SECONDS = 5
MAX_REPORT_BYTES = 50_000_000
```

403 / 429 → stop (no bypass). Every attempt (redirect / timeout / 5xx retry) consumes budget.

## Archive layout

```text
data/raw/eci/statistical_reports/report_<number>/<election_year>/<artifact-id>/
  payload.xls|xlsx
  metadata.json
  capture_report.json
```

Exact downloaded bytes are archived (never Excel resave / CSV conversion before archive).

## SOURCE_CHANGED

Logical key:

```text
Election Commission of India | election_type | election_year | report_number
```

Same SHA → `UNCHANGED`. Different SHA → `SOURCE_CHANGED` (both observations preserved).

## Persistence decision (V1)

The GitHub workflow persists **immutable acquisition artifacts only** (local archive on the
runner + `actions/upload-artifact@v4`). It does **not** open a database connection.

Future object storage (R2/S3/GCS) should implement the `CaptureStorage` protocol in
`collectors/eci/statistical_reports/storage.py` without changing capture policy.

## Workflow security

- `workflow_dispatch` only (no cron; not triggered by PR/push CI)
- `permissions: contents: read`
- concurrency group `eci-statistical-report-capture` (`cancel-in-progress: false`)
- live env flag set only in the capture step

Do not print workbook bodies, cookies, or secrets in logs.
