# ECI Statistical Reports

Historical election-result workbooks published by the Election Commission of India.

## Acquisition (manual)

See [eci-statistical-report-acquisition.md](eci-statistical-report-acquisition.md).

Capture is a **separate layer** from parsing/staging:

```text
manual GitHub Action / CLI capture
  → immutable raw archive
  → (later) offline parser / staging
  → (later) reviewed canonical reconciliation
```

This repository does **not** schedule downloads or crawl ECI.

## Relation to live results canary

The Milestone 4 canary targets `results.eci.gov.in` only and remains unchanged.
Statistical-report capture uses a different allowlist (`www.eci.gov.in`, `eci.gov.in`)
and a different env gate (`MPTA_ECI_STAT_REPORT_LIVE_ENABLED`).
