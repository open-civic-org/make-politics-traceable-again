# Live ECI election-results canary

## Status

**Disabled by default.** Opt-in only:

```bash
MPTA_ECI_LIVE_ENABLED=true \
uv run python -m collectors.eci.live_results.cli canary \
  --confirm-live \
  --capture-only
```

Both the environment flag and `--confirm-live` are required.

`--persist` is allowed only after layout validation succeeds on archived HTML. Prefer `--capture-only` for the first canary.

## Official host allowlist

```text
https://results.eci.gov.in
```

HTTPS only. No IP literals. Redirects are followed **manually** only after validating the next URL (HTTPS + allowlist + no IP literals). No third-party mirrors.

## Access-policy preflight

Automated canary runs set `robots_preflight` to **`NOT_RUN`** unless a future budgeted, archived preflight is implemented. Do not fabricate runtime robots status.

**Manual observation (2026-09-20, not part of canary execution):**

| Check | Result |
|-------|--------|
| `https://results.eci.gov.in/robots.txt` | HTTP 404 (no Disallow rules published at that path) |
| Published terms / usage restrictions | Not conclusively determined from the results host alone |
| Homepage `https://results.eci.gov.in/` | HTTP 200; meta-refresh stub → `ResultAcByeAugust2026` (active/bye surface) |
| Configured LS 2024 paths under `/PcResultGenJune2024/` | HTTP 404 |

**Policy decision:** do **not** configure or follow the August 2026 bye-election redirect for the V1 canary. Prefer historical LS 2024 URLs; when those 404, archive the statuses, fail closed on layout, and **stop expanding scope**.

When robots/terms are inconclusive, keep volume at the hard canary caps and do not escalate.

If applicable published rules later prohibit automated access: **stop** — do not bypass.

## Historical backfill strategy (next milestone)

The old counting-day HTML paths under `results.eci.gov.in` (e.g. `/PcResultGenJune2024/`) are **not** a dependable long-term historical archive. Milestone 4’s canary observed them returning 404.

Future historical ingestion should evaluate official ECI **post-election archival** surfaces separately, including:

```text
ECI Statistical Reports
ECI Result-at-a-Glance / election e-book
```

Do **not** add those hosts to this canary allowlist or fetch them here. That is a separately reviewed source-adapter milestone (fixture-first).

## Hard limits (V1)

```text
concurrency = 1
minimum interval between requests >= 5 seconds
MAX_LIVE_REQUESTS = 5   # every outbound attempt: initial, redirect hop, timeout/5xx retry
max configured URLs per canary = 5
MAX_REDIRECT_HOPS = 5
MAX_RESPONSE_BYTES = 5_000_000  # Content-Length check + streamed read
```

URLs must be explicitly listed in `collectors/eci/live_results/canary_urls.yaml`.

No pagination crawl, no state-wide enumeration, no recursive link following, no affidavit live fetching.

## Pipeline invariant

```text
HTTP response → RawArtifact → immutable archive → verify SHA-256 → parse archived bytes
```

Never parse an active HTTP response body without archiving first.

## Live SourceDocument provenance

```text
collector_name = eci_live_results
parser_version = ECI_RESULTS_HTML_PARSER_V1
extraction_method = archived_html
extraction_confidence = NULL
```

Fixture JSON keeps `eci_election_results` / `ECI_FIXTURE_JSON_PARSER_V1` / `fixture_json`.

## SOURCE_CHANGED

Same logical `source_url` with a different SHA-256 archives the new observation and opens review. Canonical `election_result` votes/rank/result are **not** mutated until an explicit review workflow approves replacement.

## Rate-limit / error policy

| Status | Action |
|--------|--------|
| 429 | Stop canary (honor Retry-After in logs; no bypass) |
| 403 | Stop canary |
| 5xx | Limited retry with backoff (each attempt consumes budget), then stop |
| timeout | Limited retry (each attempt consumes budget), then stop |
| layout change / missing geography | Fail closed — no canonical persist |

No user-agent rotation, IP rotation, proxies, or browser automation to defeat controls.

## Layout validation

Parser version: `ECI_RESULTS_HTML_PARSER_V1`.

If required markers are missing, or state/constituency/candidates cannot be positively extracted, status is `LAYOUT_CHANGED` and persist is refused. Rank is left null unless explicitly published in the source (not derived by sorting votes).

## Storage

Live archives: `data/raw/eci/results/...` (gitignored).

Only reviewed sanitized fixtures under `tests/fixtures/eci/results/`.
