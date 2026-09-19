"""Alembic upgrade/downgrade and seed idempotency against embedded Postgres."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text


def _fresh_pg() -> tuple[str, object]:
    """Always use a dedicated embedded Postgres so tests do not share state."""
    try:
        import pgserver
    except ImportError:
        if os.environ.get("DATABASE_URL"):
            # CI with service container: isolate into a fresh database name
            base = os.environ["DATABASE_URL"]
            return base, None
        pytest.skip("pgserver not installed and DATABASE_URL not set")
    datadir = Path(tempfile.mkdtemp()) / "pgdata"
    pg_handle = pgserver.get_server(datadir, cleanup_mode="delete")
    database_url = str(pg_handle.get_uri()).replace("postgresql://", "postgresql+psycopg://")
    return database_url, pg_handle


def test_alembic_upgrade_downgrade_upgrade() -> None:
    database_url, pg_handle = _fresh_pg()
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    from packages.db.session import get_engine, get_session_factory
    from packages.shared.config import get_settings

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    root = Path(__file__).resolve().parents[2]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    # Ensure alembic config uses our URL via settings/env
    cfg.set_main_option("sqlalchemy.url", database_url)

    engine = create_engine(database_url)
    with engine.begin() as conn:
        try:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        except Exception:
            pass

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "-1")
    command.upgrade(cfg, "head")

    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert heads == ["002_collector_run"]

    with engine.connect() as conn:
        tables = {
            r[0]
            for r in conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))
        }
    assert "person" in tables
    assert "source_document" in tables
    assert "asset_declaration" in tables

    get_engine.cache_clear()
    get_session_factory.cache_clear()
    if previous is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = previous
    if pg_handle is not None:
        del pg_handle


def test_seed_demo_idempotent() -> None:
    database_url, pg_handle = _fresh_pg()
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    from packages.db.session import get_engine, get_session_factory
    from packages.shared.config import get_settings

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    from packages.db import models  # noqa: F401
    from packages.db.base import Base
    from packages.db.models import (
        Affidavit,
        ElectionResult,
        ParliamentaryConstituency,
        Party,
        Person,
        SourceDocument,
    )
    from scripts.seed_demo import seed
    from sqlalchemy import func, select

    eng = get_engine()
    Base.metadata.drop_all(bind=eng)
    Base.metadata.create_all(bind=eng)

    seed()
    seed()  # second run must not duplicate

    session = get_session_factory()()
    try:
        assert session.scalar(select(func.count()).select_from(Person)) == 4
        assert session.scalar(select(func.count()).select_from(Party)) == 3
        assert session.scalar(select(func.count()).select_from(ParliamentaryConstituency)) == 4
        assert session.scalar(select(func.count()).select_from(ElectionResult)) == 4
        assert session.scalar(select(func.count()).select_from(Affidavit)) == 4
        assert session.scalar(select(func.count()).select_from(SourceDocument)) == 4
    finally:
        session.close()

    get_engine.cache_clear()
    get_session_factory.cache_clear()
    if previous is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = previous
    if pg_handle is not None:
        del pg_handle
