# Make Politics Traceable Again

Public, evidence-based tracker of elected representatives in India — from national level downward — with every material claim linked to an official source.

**Political neutrality is mandatory.** This project does not score, rank, endorse, recommend, or label politicians as good or bad. Users interpret the records.

## V1 scope

Lok Sabha only: current MPs, parties, constituencies, election history, affidavit declarations (as self-declared), parliamentary activity where reliable, and full provenance.

## Stack

| Layer | Choice |
|-------|--------|
| Web | Next.js (App Router) + TypeScript |
| API | FastAPI (Python) |
| DB | PostgreSQL + PostGIS |
| Cache / jobs | Redis |
| Object storage (dev) | MinIO |
| Migrations | Alembic |
| License | Apache-2.0 |

## Repository layout

```text
apps/web          Public website
apps/api          FastAPI REST API
apps/admin        Admin portal (scaffold)
packages/db       SQLAlchemy models + session
packages/shared   IDs, logging, config
packages/schemas  Shared Pydantic DTOs
collectors/       Official-source collectors (not live yet)
parsers/          Document parsers
migrations/       Alembic revisions
docs/             Architecture and ADRs
tests/            Unit and integration tests
```

## Quick start

```bash
cp .env.example .env
docker compose up -d postgres redis minio
uv sync --extra dev
uv run alembic upgrade head
uv run python scripts/seed_demo.py
uv run uvicorn apps.api.main:app --reload --app-dir .
# Web (separate terminal)
pnpm install
pnpm --filter mpta-web dev
```

Or: `./scripts/dev_up.sh` then start the API and web as above.

API docs: http://localhost:8000/docs  
Web: http://localhost:3000

Tests: `uv run pytest` (integration tests use `DATABASE_URL` or embedded `pgserver`).

## REST API (v1)

Unversioned:

- `GET /health`

Versioned under `/api/v1`:

- `GET /api/v1/people?q=&page=1&page_size=25`
- `GET /api/v1/people/{person_id}`
- `GET /api/v1/constituencies/{pc_id}`
- `GET /api/v1/parties/{party_id}`
- `GET /api/v1/sources/{source_id}`

People list response:

```json
{
  "items": [],
  "page": 1,
  "page_size": 25,
  "total": 0
}
```

Declared fields include provenance:

```json
{
  "value": "B.Tech",
  "declaration_year": 2024,
  "source_id": "SRC-00000001",
  "verification_status": "SELF_DECLARED"
}
```

OpenAPI: http://localhost:8000/docs

## Provenance rule

Every published claim should resolve to: person → office at that time → action/declaration → date → jurisdiction → source authority → original document.

Declarations (e.g. education on an affidavit) are shown as **self-declared**, not as independently verified facts, unless separately verified.

## Collectors

See [docs/collectors.md](docs/collectors.md). Milestone 2 delivers a fixture-mode ECI election-results pipeline (no live network).

```bash
uv run alembic upgrade head
uv run python scripts/run_eci_fixture_import.py
```


Compose configuration is implemented but **runtime smoke test is pending** on a Docker-capable host. See [docs/docker-validation.md](docs/docker-validation.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/architecture.md](docs/architecture.md).

## Security

See [SECURITY.md](SECURITY.md). Never commit secrets or large raw PDF archives.
