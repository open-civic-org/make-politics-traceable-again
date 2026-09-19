# Docker / local infrastructure validation

## Status

**Compose configuration is implemented but runtime smoke test is pending on a Docker-capable host.**

This environment did not have Docker available during foundation development. Do not treat `docker-compose.yml` as runtime-verified until the checklist below has been run successfully.

## Required smoke test (when Docker is available)

```bash
cp .env.example .env
docker compose up -d postgres redis minio
docker compose ps
```

Then verify:

1. PostgreSQL healthy (`pg_isready` / healthcheck green)
2. PostGIS extension available:

   ```bash
   docker compose exec postgres psql -U mpta -d mpta -c "CREATE EXTENSION IF NOT EXISTS postgis; SELECT PostGIS_Version();"
   ```

3. Redis reachable: `docker compose exec redis redis-cli ping` → `PONG`
4. MinIO reachable on `http://localhost:9000`
5. Alembic against container Postgres:

   ```bash
   export DATABASE_URL=postgresql+psycopg://mpta:mpta_dev_password@localhost:5432/mpta
   uv run alembic upgrade head
   uv run python scripts/seed_demo.py
   ```

This validation is a pending infrastructure item, not a blocker for committing or pushing the foundation code.
