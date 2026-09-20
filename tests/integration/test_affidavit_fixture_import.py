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
PARSE_FAILED_FIXTURE = ROOT / "tests/fixtures/eci/affidavits/asha_verma_parse_failed_amount.txt"
PDF_FIXTURE = ROOT / "tests/fixtures/eci/affidavits/asha_verma_form26.pdf"


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
    aff = session.scalars(select(Affidavit)).one()
    assert aff.candidacy_id is not None
    assert aff.election_id is not None
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


def _run_affidavit(session, tmp_path: Path, fixture: Path, **kwargs):
    from collectors.base.collector import CollectorContext
    from collectors.eci.affidavits.collector import EciAffidavitCollector

    ctx = CollectorContext(
        raw_root=tmp_path / "raw",
        failures_dir=tmp_path / "failures",
        git_commit_sha="affidavit-test-sha",
        git_dirty=False,
    )
    collector = EciAffidavitCollector(ctx, session=session, fixture_path=fixture, **kwargs)
    collector.run()
    return collector


def test_pdf_fixture_imports_with_candidacy(db_session) -> None:
    session, tmp_path = db_session
    from collectors.eci.affidavits.schemas import ParseOutcome
    from packages.db.models import Affidavit

    _seed_election(session, tmp_path)
    c = _run_affidavit(session, tmp_path, PDF_FIXTURE)
    assert c._last_outcome in {ParseOutcome.SUCCESS, ParseOutcome.PARTIAL}
    aff = session.scalars(select(Affidavit)).one()
    assert aff.candidacy_id is not None
    assert aff.election_id is not None


def test_unique_person_without_candidacy_requires_identity_review(db_session) -> None:
    session, tmp_path = db_session
    from collectors.eci.affidavits.schemas import ParseOutcome
    from packages.db.models import Affidavit, Person, ReviewItem
    from packages.shared.ids import normalize_name

    session.add(
        Person(
            person_id="IND-PER-00000999",
            canonical_name="Solo Orphan",
            normalized_name=normalize_name("Solo Orphan"),
            is_demo=True,
        )
    )
    session.flush()
    fixture = tmp_path / "solo.txt"
    fixture.write_text(
        AFFIDAVIT_FIXTURE.read_text(encoding="utf-8").replace("Asha Verma", "Solo Orphan"),
        encoding="utf-8",
    )
    c = _run_affidavit(session, tmp_path, fixture)
    assert c._last_outcome == ParseOutcome.IDENTITY_REVIEW_REQUIRED
    assert session.scalar(select(func.count()).select_from(Affidavit)) == 0
    reviews = session.scalars(
        select(ReviewItem).where(ReviewItem.review_type == "IDENTITY_REVIEW_REQUIRED")
    ).all()
    assert len(reviews) == 1


def test_wrong_election_year_requires_identity_review(db_session) -> None:
    session, tmp_path = db_session
    from collectors.eci.affidavits.schemas import ParseOutcome
    from packages.db.models import Affidavit, ReviewItem

    _seed_election(session, tmp_path)
    fixture = tmp_path / "wrong_year.txt"
    fixture.write_text(
        AFFIDAVIT_FIXTURE.read_text(encoding="utf-8").replace(
            "Election Year: 2024", "Election Year: 2019"
        ),
        encoding="utf-8",
    )
    c = _run_affidavit(session, tmp_path, fixture)
    assert c._last_outcome == ParseOutcome.IDENTITY_REVIEW_REQUIRED
    assert session.scalar(select(func.count()).select_from(Affidavit)) == 0
    assert (
        session.scalar(
            select(func.count())
            .select_from(ReviewItem)
            .where(ReviewItem.review_type == "IDENTITY_REVIEW_REQUIRED")
        )
        == 1
    )


def test_wrong_constituency_requires_identity_review(db_session) -> None:
    session, tmp_path = db_session
    from collectors.eci.affidavits.schemas import ParseOutcome
    from packages.db.models import Affidavit

    _seed_election(session, tmp_path)
    fixture = tmp_path / "wrong_pc.txt"
    fixture.write_text(
        AFFIDAVIT_FIXTURE.read_text(encoding="utf-8").replace(
            "Constituency: Demo Nagar", "Constituency: Otherville"
        ),
        encoding="utf-8",
    )
    c = _run_affidavit(session, tmp_path, fixture)
    assert c._last_outcome == ParseOutcome.IDENTITY_REVIEW_REQUIRED
    assert session.scalar(select(func.count()).select_from(Affidavit)) == 0


def test_ambiguous_candidacies_require_identity_review(db_session) -> None:
    """Person with two 2024 candidacies and affidavit missing constituency → review."""
    session, tmp_path = db_session
    from collectors.eci.affidavits.schemas import ParseOutcome
    from packages.db.models import (
        Affidavit,
        Candidacy,
        Election,
        ParliamentaryConstituency,
        Person,
        SourceDocument,
        State,
    )
    from packages.shared.ids import normalize_name

    _seed_election(session, tmp_path)
    person = session.scalars(select(Person).where(Person.canonical_name == "Asha Verma")).one()
    source = session.scalars(select(SourceDocument)).first()
    state = session.scalars(select(State)).first()
    other_pc = ParliamentaryConstituency(
        pc_id="IND-PC-00000999",
        state_id=state.state_id,
        name="Otherville",
        eci_code="OV",
    )
    session.add(other_pc)
    session.flush()
    other_el = Election(
        election_id="IND-ELC-00000999",
        election_type="LOK_SABHA",
        year=2024,
        constituency_pc_id=other_pc.pc_id,
        source_id=source.source_id,
    )
    session.add(other_el)
    session.flush()
    session.add(
        Candidacy(
            candidacy_id="IND-CND-00000999",
            person_id=person.person_id,
            election_id=other_el.election_id,
            party_id=person.current_party_id,
            candidate_name_as_published="Asha Verma",
            nomination_status="ACCEPTED",
            source_id=source.source_id,
        )
    )
    session.flush()

    fixture = tmp_path / "no_pc.txt"
    text = AFFIDAVIT_FIXTURE.read_text(encoding="utf-8")
    text = "\n".join(line for line in text.splitlines() if not line.startswith("Constituency:"))
    fixture.write_text(text + "\n", encoding="utf-8")

    c = _run_affidavit(session, tmp_path, fixture)
    assert c._last_outcome == ParseOutcome.IDENTITY_REVIEW_REQUIRED
    assert session.scalar(select(func.count()).select_from(Affidavit)) == 0
    assert normalize_name("Asha Verma") == person.normalized_name


def test_review_items_idempotent_on_reimport(db_session) -> None:
    session, tmp_path = db_session
    from packages.db.models import ReviewItem

    # OCR_REQUIRED
    _run_affidavit(session, tmp_path, OCR_FIXTURE)
    _run_affidavit(session, tmp_path, OCR_FIXTURE)
    ocr_reviews = session.scalars(
        select(ReviewItem).where(ReviewItem.review_type == "DOCUMENT_REVIEW_REQUIRED")
    ).all()
    assert len(ocr_reviews) == 1

    # IDENTITY_REVIEW_REQUIRED (person without candidacy)
    from packages.db.models import Person
    from packages.shared.ids import normalize_name

    session.add(
        Person(
            person_id="IND-PER-00000888",
            canonical_name="Review Only",
            normalized_name=normalize_name("Review Only"),
            is_demo=True,
        )
    )
    session.flush()
    identity = tmp_path / "identity.txt"
    identity.write_text(
        AFFIDAVIT_FIXTURE.read_text(encoding="utf-8").replace("Asha Verma", "Review Only"),
        encoding="utf-8",
    )
    _run_affidavit(session, tmp_path, identity)
    _run_affidavit(session, tmp_path, identity)
    id_reviews = session.scalars(
        select(ReviewItem).where(ReviewItem.review_type == "IDENTITY_REVIEW_REQUIRED")
    ).all()
    assert len(id_reviews) == 1

    # FIELD_REVIEW_REQUIRED (partial criminal section)
    _seed_election(session, tmp_path)
    _run_affidavit(session, tmp_path, PARTIAL_FIXTURE)
    before = session.scalar(
        select(func.count())
        .select_from(ReviewItem)
        .where(ReviewItem.review_type == "FIELD_REVIEW_REQUIRED")
    )
    _run_affidavit(session, tmp_path, PARTIAL_FIXTURE)
    after = session.scalar(
        select(func.count())
        .select_from(ReviewItem)
        .where(ReviewItem.review_type == "FIELD_REVIEW_REQUIRED")
    )
    assert after == before


def test_parse_failed_amount_queues_field_review(db_session) -> None:
    session, tmp_path = db_session
    from collectors.eci.affidavits.schemas import ParseOutcome
    from packages.db.models import Affidavit, AssetDeclaration, ReviewItem

    _seed_election(session, tmp_path)
    c = _run_affidavit(session, tmp_path, PARSE_FAILED_FIXTURE)
    assert c._last_outcome == ParseOutcome.PARTIAL
    aff = session.scalars(select(Affidavit)).one()
    assert aff.candidacy_id is not None
    asset = session.scalars(select(AssetDeclaration)).one()
    assert asset.field_status == "PARSE_FAILED"
    assert asset.declared_value_inr is None
    assert asset.amount_raw == "approx lots of money"
    reviews = session.scalars(
        select(ReviewItem).where(
            ReviewItem.review_type == "FIELD_REVIEW_REQUIRED",
            ReviewItem.field_name == "assets.TOTAL_ASSETS",
        )
    ).all()
    assert len(reviews) == 1
    assert reviews[0].raw_text == "approx lots of money"
    assert reviews[0].affidavit_id == aff.affidavit_id
    assert reviews[0].parser_version
