# ECI statistical-report acquisition (manual GitHub Action)

## Purpose

Authorized maintainers can capture **one** official ECI statistical-report workbook via a
manual GitHub Actions workflow. Capture is **acquisition only**:

```text
manual workflow_dispatch
  → validate URL / host allowlist
  → guarded HTTPS download (exact bytes)
  → immutable raw archive + SHA-256 + metadata
  → upload GitHub Actions artifact (temporary V1 transport)
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

## Report number

`report_number` is a **positive integer** only:

```text
1 <= report_number <= 9999
```

It is validated before any archive path or artifact name is constructed. Canonical form
is the digit string (e.g. `33` → path component `report_33`). Path traversal / free-form
strings are rejected.

## Format detection

Do not trust URL extension / Content-Type alone. Capture inspects bytes:

```text
HTML markers                         → CAPTURE_REJECTED
OOXML ZIP with [Content_Types].xml
  + xl/workbook.xml                  → xlsx
generic / incomplete / corrupt ZIP   → CAPTURE_REJECTED
OLE/CFB magic (D0 CF 11 E0…)         → OLE_CFB  (not asserted as Excel)
```

OLE compound files are archived as `payload.ole` with `detected_container_format=OLE_CFB`
until a later workbook extractor proves Excel content.

## Archive layout

```text
data/raw/eci/statistical_reports/report_<number>/<election_year>/<artifact-id>/
  payload.xlsx|ole|bin
  metadata.json
  capture_report.json
```

Exact downloaded bytes are archived (never Excel resave / CSV conversion before archive).

## Source status (local archive root only)

Logical key:

```text
Election Commission of India | election_type | election_year | report_number
```

When the **same persistent `raw_root`** already contains a prior observation:

```text
same SHA       → UNCHANGED
different SHA  → SOURCE_CHANGED   (both observations preserved)
```

When **no prior state** exists under `raw_root` (typical fresh GitHub-hosted runner):

```text
FIRST_OBSERVATION
```

GitHub Actions artifacts are **not** restored onto later runners. Cross-run
`UNCHANGED` / `SOURCE_CHANGED` is therefore **not** available in V1 workflow runs.
True durable comparison requires later persistent storage (R2 / S3-compatible / DB
source-observation registry).

## Persistence decision (V1)

The GitHub workflow persists acquisition outputs as:

1. an immutable archive directory on the ephemeral runner, then
2. `actions/upload-artifact@v4` with **`retention-days: 30`**.

**The GitHub Actions artifact is NOT the permanent evidence archive.** After 30 days
it may no longer be available. Bytes are immutable while stored; multi-year durability
requires the later object-storage milestone.

The workflow does **not** open a database connection and does not mutate canonical rows.

Future object storage (R2/S3/GCS) should implement the `CaptureStorage` protocol in
`collectors/eci/statistical_reports/storage.py` without changing capture policy.

## Workflow security

- `workflow_dispatch` only (no cron; not triggered by PR/push CI)
- `permissions: contents: read`
- concurrency group `eci-statistical-report-capture` (`cancel-in-progress: false`)
- live env flag set only in the capture step
- workflow_dispatch inputs are mapped via step `env:` and passed as quoted shell
  variables (`$ECI_REPORT_*`) — never interpolated into shell source with `${{ inputs.* }}`

Do not print workbook bodies, cookies, or secrets in logs.

## Related: OGD CSV primary path (2024 Report 33)

While ECI XLS returns HTTP 406 from automated clients, Milestone 5 uses the
data.gov.in CSV distribution as the primary archive. See
[ogd-constituency-wise-detailed-result-2024.md](ogd-constituency-wise-detailed-result-2024.md).
This workflow remains the official-host XLS provenance tool and must not be
used to bypass WAF controls.
