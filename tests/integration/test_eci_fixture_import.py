"""Fixture-mode ECI collector end-to-end against embedded Postgres."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/eci/election_results/ge2024_demo_nagar.json"


def _fresh_db():
    try:
        import pgserver
    except ImportError:
        if not os.environ.get("DATABASE_URL"):
            pytest.skip("no postgres")
        url = os.environ["DATABASE_URL"]
        return url, None
    datadir = Path(tempfile.mkdtemp()) / "pgdata"
    handle = pgserver.get_server(datadir, cleanup_mode="delete")
    url = str(handle.get_uri()).replace("postgresql://", "postgresql+psycopg://")
    return url, handle


@pytest.fixture()
def db_session(tmp_path: Path):
    url, handle = _fresh_db()
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    os.environ["MPTA_GIT_COMMIT_SHA"] = "fixture-test-sha"

    from packages.db.session import get_engine, get_session_factory
    from packages.shared.config import get_settings

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    from packages.db import models  # noqa: F401
    from packages.db.base import Base

    eng = get_engine()
    Base.metadata.create_all(bind=eng)
    Session = get_session_factory()
    session = Session()
    yield session, tmp_path
    session.close()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    get_settings.cache_clear()
    if previous is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = previous
    os.environ.pop("MPTA_GIT_COMMIT_SHA", None)
    if handle is not None:
        del handle


def test_eci_fixture_import_idempotent(db_session) -> None:
    session, tmp_path = db_session
    from collectors.base.collector import CollectorContext
    from collectors.eci.collector import EciElectionResultsCollector
    from packages.db.models import (
        Candidacy,
        CollectorRun,
        Election,
        ElectionResult,
        Person,
        SourceDocument,
    )

    raw_root = tmp_path / "raw"
    failures = tmp_path / "failures"
    ctx = CollectorContext(
        raw_root=raw_root,
        failures_dir=failures,
        git_commit_sha="fixture-test-sha",
        git_dirty=False,
    )

    c1 = EciElectionResultsCollector(ctx, session=session, fixture_path=FIXTURE)
    stats1 = c1.run()
    assert stats1.records_valid == 5
    assert session.scalar(select(func.count()).select_from(Election)) == 1
    assert session.scalar(select(func.count()).select_from(Candidacy)) == 5
    assert session.scalar(select(func.count()).select_from(ElectionResult)) == 5
    people_count = session.scalar(select(func.count()).select_from(Person))
    sources = session.scalar(select(func.count()).select_from(SourceDocument))
    assert people_count == 5
    assert sources == 1

    # Provenance on results
    result = session.scalars(select(ElectionResult)).first()
    assert result is not None
    assert result.source_id.startswith("SRC-")
    src = session.get(SourceDocument, result.source_id)
    assert src is not None
    assert src.content_sha256
    assert src.collector_name == "eci_election_results"
    assert src.git_commit_sha == "fixture-test-sha"
    assert src.archived_path

    run = session.scalars(select(CollectorRun)).first()
    assert run is not None
    assert run.status == "SUCCESS"

    # Second run: no duplicate candidacies / elections
    ctx2 = CollectorContext(
        raw_root=raw_root,
        failures_dir=failures,
        git_commit_sha="fixture-test-sha",
        git_dirty=False,
    )
    c2 = EciElectionResultsCollector(ctx2, session=session, fixture_path=FIXTURE)
    c2.run()
    assert session.scalar(select(func.count()).select_from(Election)) == 1
    assert session.scalar(select(func.count()).select_from(Candidacy)) == 5
    assert session.scalar(select(func.count()).select_from(ElectionResult)) == 5
    assert session.scalar(select(func.count()).select_from(Person)) == people_count
    assert session.scalar(select(func.count()).select_from(SourceDocument)) == 1

    # Archive exists and verifies
    from collectors.base.archive import verify_artifact

    archives = list((raw_root / "eci" / "election_results" / "2024").iterdir())
    assert archives
    verify_artifact(archives[0])
