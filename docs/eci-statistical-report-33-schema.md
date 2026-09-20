# ECI Statistical Report 33 — observed schema

## Capture status

| Field | Value |
|-------|-------|
| Source landing page | `https://www.eci.gov.in/general-election-to-loksabha-2024-statistical-reports` |
| Official PDF | `https://www.eci.gov.in/eci-backend/public/all_files/GE-2024-statistical-report/33-Constituency-Wise-Detailed-Result.pdf` |
| Official XLS/XLSX attempt | **BLOCKED_WAF_APPTRANA_406** (AppTrana WAF from this environment) |
| Live ECI HTTP probes (Phase 0) | ~12 requests (landing + file probes); all non-workbook responses |
| Offline archive note | `data/raw/eci/statistical_reports/2024/report_33/` (gitignored) |
| Fixture | `tests/fixtures/eci/statistical_reports/report33/report33_schema_fixture.xls` |
| Fixture SHA-256 | `319e5d17e74f882272616fb8dd9add82bb7188c4ae08ae6af88489ead89bcfc8` |
| Container | Legacy OLE Compound File Binary (CFB) `.xls` |
| Magic bytes | `d0 cf 11 e0` (`\xd0\xcf\x11\xe0`) |
| Sheet | `Detailed Results` |

Header labels match the published Report 33 PDF field sequence. Candidate / constituency cell values in the fixture are **fictionalized**. The full official workbook was **not** obtained; do not treat the fixture SHA as the official ECI workbook SHA.

## Headers (row 0)

Exact observed headers (17 columns):

1. State Name
2. PC Name
3. Candidate Name
4. Gender
5. Age
6. Category
7. Party Name
8. Party Symbol
9. Total Votes Polled In The Constituency
10. Valid Votes
11. Votes Secured - General
12. Votes Secured - Postal
13. Votes Secured - Total
14. % of Votes Secured - Over Total Electors In Constituency
15. % of Votes Secured - Over Total Votes Polled In Constituency
16. Over Total Valid Votes Polled In Constituency
17. Total Electors

## Semantic mapping (staging)

| Header | Staging field |
|--------|---------------|
| Votes Secured - Total | `votes_*` (primary vote count) |
| Over Total Valid Votes Polled In Constituency | `vote_share_*` (primary share) |
| (no rank column) | `rank` always `NULL` |
| (no result column) | `result_normalized` = `UNKNOWN` (never invent WON/LOST) |

## Coverage contract

ECI GE-2024 Statistical Report 33 discloses **542** parliamentary constituencies. Staging coverage reports document that published scope. A tiny schema fixture with fewer PCs is marked `UNKNOWN` / `fixture_subset` — **not** treated as a hard production failure.

## Parser version

`ECI_LS2024_REPORT33_PARSER_V1`
