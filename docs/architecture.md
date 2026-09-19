# Architecture

## Goals

- Traceable public records of elected representatives
- Political neutrality (no scores, rankings, or endorsements)
- Rebuildability from archived raw sources
- Accuracy and auditability over record count

## System overview

```text
Official sources
    → collectors (fetch + archive raw)
    → parsers (extract structured fields)
    → normalize + validate
    → upsert into PostgreSQL with source_document
    → REST API
    → public web / admin
```

Raw artifacts (PDFs, HTML) live in object storage (MinIO locally; S3/R2/GCS in production). They are not stored in Git.

## Monorepo

| Path | Role |
|------|------|
| `apps/api` | FastAPI REST API + OpenAPI |
| `apps/web` | Public Next.js site |
| `apps/admin` | Identity/data review (scaffold) |
| `packages/db` | SQLAlchemy models, engine, session |
| `packages/shared` | ID generation, logging, config |
| `packages/schemas` | Shared Pydantic response models |
| `packages/identity` | Match review (stub) |
| `collectors/*` | Per-authority collectors |
| `parsers/*` | Affidavit/election/parliament parsers |
| `migrations/` | Alembic revisions |

## Identifier scheme

Stable string IDs — never use names as primary keys.

| Entity | Pattern | Example |
|--------|---------|---------|
| Person | `IND-PER-{8 digit}` | `IND-PER-00000001` |
| Party | `IND-PTY-{8 digit}` | `IND-PTY-00000001` |
| Source | `SRC-{8 digit}` | `SRC-00000001` |
| Office | `IND-OFC-{8 digit}` | `IND-OFC-00000001` |
| Election | `IND-ELC-{8 digit}` | `IND-ELC-00000001` |
| Affidavit | `IND-AFD-{8 digit}` | `IND-AFD-00000001` |
| Constituency (PC) | `IND-PC-{8 digit}` | `IND-PC-00000001` |

People store both `canonical_name` (display) and `normalized_name` (matching aid). Affidavit declaration text fields (`declared_education`, etc.) preserve source wording; they are not independently verified facts.

Money amounts (`declared_value_inr` on assets/liabilities/income) use PostgreSQL `NUMERIC(18,2)`, not floating-point types.

## Public API

Unversioned: `GET /health`  
Versioned prefix: `/api/v1/...` (people, constituencies, parties, sources). No legacy `/api/*` aliases.

## Local infrastructure

See [docker-validation.md](docker-validation.md). Compose is configured; runtime smoke test is pending where Docker is unavailable.

## Provenance chain

Every material claim should resolve to:

```text
Person
 → Office at that time
 → Action / Declaration
 → Date
 → Jurisdiction
 → Source authority
 → Original source document (URL + SHA-256 + retrieval metadata)
```

`source_document` stores authority, URL, content hash, collector/parser versions, git commit SHA, extraction method, confidence, and verification status.

## Declarations vs verified facts

Affidavit fields (education, profession, assets, liabilities, cases, income) are stored as **declarations** tied to an affidavit and source. UI copy must say they were declared in an election affidavit, not that they are independently verified, unless a separate verification record exists.

Criminal cases: show disposition explicitly (declared pending, charge, conviction, acquittal, dismissal). Never label a person “criminal” merely because an affidavit lists a pending case.

## Historical records

Office terms, candidacies, and results are append-oriented. Collectors must not silently overwrite conflicting historical data; conflicts surface for review.

## Geography

Hierarchical: India → State/UT → District → Parliamentary / Assembly constituencies (and later municipal/rural units). PostGIS is enabled; geometry columns come later.

## V1 delivery

Lok Sabha MPs only. State and local government collectors wait until the Lok Sabha pipeline is stable.

## Neutrality

Do not build: best/worst politician, corruption/performance scores, voting recommendations, or party rankings. Measurable records (questions asked, attendance, results, declared assets) may be shown without interpretive scores.
