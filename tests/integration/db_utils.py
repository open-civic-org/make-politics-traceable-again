"""Shared helpers for integration tests that need a clean Postgres schema."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine


def reset_public_schema(engine: Engine) -> None:
    """
    Drop and recreate `public` so create_all/alembic start from a clean slate.

    Needed in CI where Alembic has already migrated the shared PostGIS service
    and a leftover/non-app `state` relation can break FK creation for `district`.
    """
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.execute(text("GRANT ALL ON SCHEMA public TO CURRENT_USER"))
        conn.execute(text("GRANT ALL ON SCHEMA public TO public"))
        try:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        except Exception:
            # Extension may require superuser; app schema still usable without it.
            pass
