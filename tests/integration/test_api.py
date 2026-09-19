from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    """Prefer embedded pgserver; fall back to DATABASE_URL (CI) with schema reset."""
    pg_handle = None
    owned_url = False
    database_url: str | None = None

    try:
        import pgserver

        datadir = Path(tempfile.mkdtemp()) / "pgdata"
        pg_handle = pgserver.get_server(datadir, cleanup_mode="delete")
        database_url = str(pg_handle.get_uri()).replace("postgresql://", "postgresql+psycopg://")
        owned_url = True
    except ImportError:
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            pytest.skip("DATABASE_URL not set and pgserver not installed")

    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url

    from packages.db.session import get_engine, get_session_factory
    from packages.shared.config import get_settings

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    from apps.api.deps import get_db
    from apps.api.main import app
    from packages.db import models  # noqa: F401
    from packages.db.base import Base
    from scripts.seed_demo import seed
    from tests.integration.db_utils import reset_public_schema

    eng = get_engine()
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
            conn.commit()
    except Exception as exc:  # noqa: BLE001
        if pg_handle is not None:
            del pg_handle
        pytest.skip(f"PostgreSQL not available: {exc}")

    # Shared CI PostGIS may already be migrated; always start clean.
    reset_public_schema(eng)
    Base.metadata.create_all(bind=eng)
    seed()

    session_factory = get_session_factory()

    def _override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    get_settings.cache_clear()
    if owned_url:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
    if pg_handle is not None:
        del pg_handle
