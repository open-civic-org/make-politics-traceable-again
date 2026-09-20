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

HTTPS only. No IP literals. Redirects must stay on this host. No third-party mirrors.

## Access-policy preflight (2026-09-20)

| Check | Result |
|-------|--------|
| `https://results.eci.gov.in/robots.txt` | **HTTP 404** (no Disallow rules published at that path) |
| Published terms / usage restrictions | Not conclusively determined from the results host alone |
| Homepage `https://results.eci.gov.in/` | HTTP 200; meta-refresh stub → `ResultAcByeAugust2026` (active/bye surface) |
| Configured LS 2024 paths under `/PcResultGenJune2024/` | **HTTP 404** from this environment during Milestone 4 preflight |

**Policy decision:** do **not** configure or follow the August 2026 bye-election redirect for the V1 canary. Prefer historical LS 2024 URLs; when those 404, archive the statuses, fail closed on layout, and **stop expanding scope**.

When robots/terms are inconclusive, keep volume at the hard canary caps and do not escalate.

If applicable published rules later prohibit automated access: **stop** — do not bypass.

## Hard limits (V1)

```text
concurrency = 1
minimum interval between requests >= 5 seconds
MAX_LIVE_REQUESTS = 5
max configured URLs per canary = 5
```

URLs must be explicitly listed in `collectors/eci/live_results/canary_urls.yaml`.

No pagination crawl, no state-wide enumeration, no recursive link following, no affidavit live fetching.

## Pipeline invariant

```text
HTTP response → RawArtifact → immutable archive → verify SHA-256 → parse archived bytes
```

Never parse an active HTTP response body without archiving first.

## Rate-limit / error policy

| Status | Action |
|--------|--------|
| 429 | Stop canary (honor Retry-After in logs; no bypass) |
| 403 | Stop canary |
| 5xx | Limited retry with backoff, then stop |
| timeout | Limited retry, then stop |
| layout change | Fail closed — no canonical persist |

No user-agent rotation, IP rotation, proxies, or browser automation to defeat controls.

## Layout validation

Parser version: `ECI_RESULTS_HTML_PARSER_V1`.

If required markers are missing, status is `LAYOUT_CHANGED` and persist is refused.

## Storage

Live archives: `data/raw/eci/results/...` (gitignored).

Only reviewed sanitized fixtures under `tests/fixtures/eci/results/`.
