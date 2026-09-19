"""Fixture-mode ECI affidavit collector end-to-end against embedded Postgres."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[2]
ELECTION_FIXTURE = ROOT / "tests/fixtures/eci/election_results/ge2024_demo_nagar.json"
AFFIDAVIT_FIXTURE = ROOT / "tests/fixtures/eci/affidavits/asha_verma_form26.txt"
PARTIAL_FIXTURE = ROOT / "tests/fixtures/eci/affidavits/bharat_mehta_partial.txt"
OCR_FIXTURE = ROOT / "tests/fixtures/eci/affidavits/scanned_ocr_required.bin"


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
    os.environ["MPTA_GIT_COMMIT_SHA"] = "affidavit-test-sha"

    from packages.db.session import get_engine, get_session_factory
    from packages.shared.config import get_settings

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    from packages.db import models  # noqa: F401
    from packages.db.base import Base
    from tests.integration.db_utils import reset_public_schema

    eng = get_engine()
    reset_public_schema(eng)
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


def _seed_election(session, tmp_path: Path) -> None:
    from collectors.base.collector import CollectorContext
    from collectors.eci.collector import EciElectionResultsCollector

    ctx = CollectorContext(
        raw_root=tmp_path / "raw",
        failures_dir=tmp_path / "failures",
        git_commit_sha="affidavit-test-sha",
        git_dirty=False,
    )
    EciElectionResultsCollector(ctx, session=session, fixture_path=ELECTION_FIXTURE).run()


def test_affidavit_import_idempotent(db_session) -> None:
    session, tmp_path = db_session
    from collectors.base.collector import CollectorContext
    from collectors.eci.affidavits.collector import EciAffidavitCollector
    from collectors.eci.affidavits.schemas import ParseOutcome
    from packages.db.models import (
        Affidavit,
        AssetDeclaration,
        CriminalCaseDeclaration,
        EducationDeclaration,
        LiabilityDeclaration,
        SourceDocument,
    )

    _seed_election(session, tmp_path)

    ctx = CollectorContext(
        raw_root=tmp_path / "raw",
        failures_dir=tmp_path / "failures",
        git_commit_sha="affidavit-test-sha",
        git_dirty=False,
    )
    c1 = EciAffidavitCollector(ctx, session=session, fixture_path=AFFIDAVIT_FIXTURE)
    stats1 = c1.run()
    assert stats1.records_valid == 1
    assert c1._last_outcome in {ParseOutcome.SUCCESS, ParseOutcome.PARTIAL}

    assert session.scalar(select(func.count()).select_from(Affidavit)) == 1
    assert session.scalar(select(func.count()).select_from(EducationDeclaration)) == 1
    assert session.scalar(select(func.count()).select_from(AssetDeclaration)) == 3
    assert session.scalar(select(func.count()).select_from(LiabilityDeclaration)) == 1
    assert session.scalar(select(func.count()).select_from(CriminalCaseDeclaration)) == 0

    edu = session.scalars(select(EducationDeclaration)).one()
    assert edu.normalized_level == "GRADUATE"
    assert edu.declared_value_raw == "Bachelor of Engineering"

    total = session.scalars(
        select(AssetDeclaration).where(AssetDeclaration.asset_category == "TOTAL_ASSETS")
    ).one()
    assert total.amount_raw == "Rs. 1,23,45,678"
    assert str(total.declared_value_inr) == "12345678.00"
    assert total.currency == "INR"

    sources_before = session.scalar(select(func.count()).select_from(SourceDocument))

    ctx2 = CollectorContext(
        raw_root=tmp_path / "raw",
        failures_dir=tmp_path / "failures",
        git_commit_sha="affidavit-test-sha",
        git_dirty=False,
    )
    c2 = EciAffidavitCollector(ctx2, session=session, fixture_path=AFFIDAVIT_FIXTURE)
    c2.run()
    assert c2._last_outcome == ParseOutcome.UNCHANGED

    assert session.scalar(select(func.count()).select_from(Affidavit)) == 1
    assert session.scalar(select(func.count()).select_from(EducationDeclaration)) == 1
    assert session.scalar(select(func.count()).select_from(AssetDeclaration)) == 3
    assert session.scalar(select(func.count()).select_from(LiabilityDeclaration)) == 1
    assert session.scalar(select(func.count()).select_from(SourceDocument)) == sources_before


def test_partial_parse_queues_field_review(db_session) -> None:
    session, tmp_path = db_session
    from collectors.base.collector import CollectorContext
    from collectors.eci.affidavits.collector import EciAffidavitCollector
    from collectors.eci.affidavits.schemas import ParseOutcome
    from packages.db.models import Affidavit, EducationDeclaration, ReviewItem

    _seed_election(session, tmp_path)
    ctx = CollectorContext(
        raw_root=tmp_path / "raw",
        failures_dir=tmp_path / "failures",
        git_commit_sha="affidavit-test-sha",
        git_dirty=False,
    )
    c = EciAffidavitCollector(ctx, session=session, fixture_path=PARTIAL_FIXTURE)
    c.run()
    assert c._last_outcome == ParseOutcome.PARTIAL
    assert session.scalar(select(func.count()).select_from(EducationDeclaration)) == 1
    assert session.scalar(select(func.count()).select_from(Affidavit)) == 1
    reviews = session.scalars(
        select(ReviewItem).where(ReviewItem.review_type == "FIELD_REVIEW_REQUIRED")
    ).all()
    assert len(reviews) >= 1


def test_ocr_required_no_empty_declarations(db_session) -> None:
    session, tmp_path = db_session
    from collectors.base.collector import CollectorContext
    from collectors.eci.affidavits.collector import EciAffidavitCollector
    from packages.db.models import Affidavit, EducationDeclaration, ReviewItem

    ctx = CollectorContext(
        raw_root=tmp_path / "raw",
        failures_dir=tmp_path / "failures",
        git_commit_sha="affidavit-test-sha",
        git_dirty=False,
    )
    c = EciAffidavitCollector(ctx, session=session, fixture_path=OCR_FIXTURE)
    c.run()
    assert session.scalar(select(func.count()).select_from(Affidavit)) == 0
    assert session.scalar(select(func.count()).select_from(EducationDeclaration)) == 0
    reviews = session.scalars(
        select(ReviewItem).where(ReviewItem.review_type == "DOCUMENT_REVIEW_REQUIRED")
    ).all()
    assert len(reviews) == 1
    assert "OCR_REQUIRED" in reviews[0].reason


def test_source_changed_preserves_both(db_session) -> None:
    session, tmp_path = db_session
    from collectors.base.collector import CollectorContext
    from collectors.eci.affidavits.collector import EciAffidavitCollector
    from collectors.eci.affidavits.schemas import ParseOutcome
    from packages.db.models import Affidavit, SourceDocument

    _seed_election(session, tmp_path)
    url = "fixture://eci/affidavits/mutation-test"

    ctx = CollectorContext(
        raw_root=tmp_path / "raw",
        failures_dir=tmp_path / "failures",
        git_commit_sha="affidavit-test-sha",
        git_dirty=False,
    )
    EciAffidavitCollector(
        ctx, session=session, fixture_path=AFFIDAVIT_FIXTURE, source_url=url
    ).run()

    # Mutated bytes, same logical URL
    mutated = tmp_path / "mutated.txt"
    mutated.write_text(
        AFFIDAVIT_FIXTURE.read_text(encoding="utf-8") + "\n# observation-2\n",
        encoding="utf-8",
    )
    ctx2 = CollectorContext(
        raw_root=tmp_path / "raw",
        failures_dir=tmp_path / "failures",
        git_commit_sha="affidavit-test-sha",
        git_dirty=False,
    )
    c2 = EciAffidavitCollector(ctx2, session=session, fixture_path=mutated, source_url=url)
    c2.run()
    assert c2._last_outcome == ParseOutcome.SOURCE_CHANGED
    assert session.scalar(select(func.count()).select_from(Affidavit)) == 2
    assert session.scalar(select(func.count()).select_from(SourceDocument)) >= 2
