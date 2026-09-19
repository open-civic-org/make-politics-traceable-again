#!/usr/bin/env bash
set -euo pipefail
cp -n .env.example .env || true
docker compose up -d postgres redis minio
echo "Waiting for Postgres..."
until docker compose exec -T postgres pg_isready -U mpta -d mpta >/dev/null 2>&1; do sleep 1; done
uv sync --extra dev
uv run alembic upgrade head
uv run python scripts/seed_demo.py
echo "Foundation services ready. Run API: uv run uvicorn apps.api.main:app --reload --app-dir ."
echo "Run web: pnpm --filter mpta-web dev"
