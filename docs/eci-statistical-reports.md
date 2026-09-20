# ECI Statistical Reports

Historical election-result workbooks published by the Election Commission of India.

## 2024 Lok Sabha Report 33 — primary path

**ECI XLS is currently blocked (HTTP 406 / AppTrana)** from GitHub Actions and
typical automated clients. Milestone 5 therefore uses the **data.gov.in CSV**
distribution of the same ECI-sourced dataset as the primary ingestion source.

See [ogd-constituency-wise-detailed-result-2024.md](ogd-constituency-wise-detailed-result-2024.md).

```text
PRIMARY:   data.gov.in CSV (OGD / sourced from ECI)
SECONDARY: Lok Dhaba / TCPD validation
AFFIDAVIT: ECI Form-26 + MyNeta/ADR index
TERTIARY:  independent scrapes (forensic only)
```

## Acquisition (manual ECI XLS workflow)

See [eci-statistical-report-acquisition.md](eci-statistical-report-acquisition.md).

The GitHub Action remains available for official-host workbook capture when the
ECI CDN allows it. It does **not** block CSV-based staging.

Capture is a **separate layer** from parsing/staging:

```text
manual acquisition (OGD CSV or ECI workbook)
  → immutable raw archive
  → (later) offline parser / staging
  → (later) reviewed canonical reconciliation
```

This repository does **not** schedule downloads or crawl ECI / data.gov.in.

**GitHub Actions artifact retention (30 days) is temporary V1 transport only.**
It is **not** the permanent evidence archive. Durable multi-year storage requires
later R2/S3-compatible object storage.

## Relation to live results canary

The Milestone 4 canary targets `results.eci.gov.in` only and remains unchanged.
Statistical-report capture uses a different allowlist (`www.eci.gov.in`, `eci.gov.in`)
and a different env gate (`MPTA_ECI_STAT_REPORT_LIVE_ENABLED`).
