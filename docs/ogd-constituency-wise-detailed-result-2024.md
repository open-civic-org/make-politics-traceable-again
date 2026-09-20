# 2024 Lok Sabha constituency-wise results — source plan

## Decision (post attempted ECI XLS 406)

An **attempted** ECI Report 33 XLS path (inferred from the published GE-2024
statistical-report file layout; **not** copied from a verified download href)
returned **HTTP 406 from ECI edge/WAF** from both local probes and a
GitHub-hosted runner. See workflow run:

https://github.com/open-civic-org/make-politics-traceable-again/actions/runs/35534730905

That does **not** block Milestone 5. Prefer the Government of India Open
Government Data (OGD) CSV distribution corresponding to the ECI
Constituency-wise Detailed Result statistical report (OGD metadata: sourced
from ECI). We have **not** compared inaccessible ECI workbook bytes to the CSV.

## Primary source (Milestone 5)

| Field | Value |
|-------|-------|
| Title | Constituency-wise Detailed Result during 2024 |
| Catalog | General Election to Lok Sabha 2024 - Statistical Reports Data |
| Distribution | [data.gov.in resource page](https://www.data.gov.in/resource/constituency-wise-detailed-result-during-2024) |
| Format | **CSV** (~1.0 MB) |
| Published | 2025-01-16 (per OGD metadata) |
| Scope | 542 PCs; **excludes Surat (PC-24)** uncontested — same note as ECI |

Provenance fields for archive metadata:

```text
source_authority         = Election Commission of India
distribution_authority   = Open Government Data Platform India
source_type              = ELECTION_STATISTICAL_REPORT
source_format            = CSV
report_number            = 33   # logical ECI report identity
report_title             = Constituency Wise Detailed Result
election_type            = LOK_SABHA
election_year            = 2024
```

URLs to retain in provenance:

```text
distribution_url =
  https://www.data.gov.in/resource/constituency-wise-detailed-result-during-2024

eci_reference_url =
  https://www.eci.gov.in/general-election-to-loksabha-2024-statistical-reports

eci_attempted_xls_url =
  https://www.eci.gov.in/eci-backend/public/all_files/GE-2024-statistical-report/33-Constituency-Wise-Detailed-Result.xls
```

`eci_attempted_xls_url` is an **attempted acquisition URL** (inferred path that
returned HTTP 406). It is **not** a verified canonical ECI distribution href.
`eci_reference_url` is the ECI landing/reference page for 2024 statistical reports.

### Acquisition procedure (V1)

data.gov.in currently gates downloads behind **registered-user** sessions and
does not expose a sourced API for this catalog. Automated collectors must **not**
attempt login bypass.

```text
1. Human: sign in to data.gov.in in a normal browser
2. Download the CSV for “Constituency-wise Detailed Result during 2024”
3. Do not open/resave in Excel; preserve exact bytes
4. Before opening elsewhere: record original filename, byte size,
   UTC retrieval time, resource URL, SHA-256
5. Place under immutable archive (same archive framework as ECI capture)
6. Record metadata (authorities, distribution + ECI reference URLs,
   optional attempted XLS URL labeled as such, retrieved_at, sha256, size)
7. Offline parser builds from that exact file + fixture derived from it
```

Suggested archive layout (reuse existing raw framework):

```text
data/raw/ogd/statistical_reports/report_33/2024/<artifact-id>/
  payload.csv
  metadata.json
```

## Secondary / supporting sources

| Role | Source | Use |
|------|--------|-----|
| Secondary validation | Lok Dhaba / TCPD (Ashoka) | Reconciliation; later person-ID hints |
| Affidavit enrichment | ECI Form-26 originals + MyNeta/ADR | Not vote-count authority |
| Tertiary cross-check | Independent GitHub ECI scrapes | Forensic only — not canonical |

## ECI XLS capture workflow

Keep `.github/workflows/eci-statistical-report-capture.yml` as an official-host
provenance tool. It remains `workflow_dispatch` only. It must **not** gate
Milestone 5 while automated ECI workbook fetch returns HTTP 406. Do not add
header-spoofing / WAF bypass. Only use a verified XLS download href (copied
from ECI UI) when one is available — never promote an inferred path to
canonical `distribution_url`.

## Parser implication

Primary path is **CSV**, not legacy OLE/XLS. Milestone 5 should parse the OGD
CSV deterministically offline. OLE_CFB / XLSX detectors stay relevant for any
future successful ECI workbook capture, not for the primary 2024 ingestion path.
