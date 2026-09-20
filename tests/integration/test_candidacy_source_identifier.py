"""External candidacy source identifiers and provenance cleanup."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[2]
ELECTION_FIXTURE = ROOT / "tests/fixtures/eci/election_results/ge2024_demo_nagar.json"
AFFIDAVIT_FIXTURE = ROOT / "tests/fixtures/eci/affidavits/asha_verma_form26.txt"
PDF_FIXTURE = ROOT / "tests/fixtures/eci/affidavits/asha_verma_form26.pdf"


def _fresh_db():
    try:
        import pgserver
    except ImportError:
        if not os.environ.get("DATABASE_URL"):
            pytest.skip("no postgres")
        return os.environ["DATABASE_URL"], None
    datadir = Path(tempfile.mkdtemp()) / "pgdata"
    handle = pgserver.get_server(datadir, cleanup_mode="delete")
    url = str(handle.get_uri()).replace("postgresql://", "postgresql+psycopg://")
    return url, handle


@pytest.fixture()
def db_session(tmp_path: Path):
    url, handle = _fresh_db()
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    os.environ["MPTA_GIT_COMMIT_SHA"] = "identity-test-sha"

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


def _seed_election(session, tmp_path: Path):
    from collectors.base.collector import CollectorContext
    from collectors.eci.collector import EciElectionResultsCollector

    ctx = CollectorContext(
        raw_root=tmp_path / "raw",
        failures_dir=tmp_path / "failures",
        git_commit_sha="identity-test-sha",
        git_dirty=False,
    )
    EciElectionResultsCollector(ctx, session=session, fixture_path=ELECTION_FIXTURE).run()


def test_external_id_maps_to_candidacy_not_person_pk(db_session) -> None:
    session, tmp_path = db_session
    from packages.db.models import CandidacySourceIdentifier, Person
    from packages.shared.identity import lookup_candidacy_by_external_id

    _seed_election(session, tmp_path)

    # External ID must not be a Person PK
    assert session.get(Person, "ECI-DEMO-CAND-001") is None

    csi = session.scalars(
        select(CandidacySourceIdentifier).where(
            CandidacySourceIdentifier.external_value_raw == "ECI-DEMO-CAND-001"
        )
    ).one()
    assert csi.identifier_type == "CANDIDATE_ID"
    assert csi.source_system == "RESULTS_PORTAL"

    candidacy = lookup_candidacy_by_external_id(session, external_value_raw="ECI-DEMO-CAND-001")
    assert candidacy is not None
    assert candidacy.candidacy_id == csi.candidacy_id
    person = session.get(Person, candidacy.person_id)
    assert person is not None
    assert person.canonical_name == "Asha Verma"
    assert person.person_id.startswith("IND-PER-")


def test_duplicate_external_id_same_scope_cannot_remap(db_session) -> None:
    session, tmp_path = db_session
    from packages.db.models import Candidacy, Election, Person
    from packages.shared.identity import (
        SOURCE_SYSTEM_RESULTS,
        attach_candidacy_source_identifier,
    )

    _seed_election(session, tmp_path)
    election = session.scalars(select(Election)).one()
    asha_cnd = session.scalars(
        select(Candidacy).join(Person).where(Person.canonical_name == "Asha Verma")
    ).one()
    other_cnd = session.scalars(
        select(Candidacy).join(Person).where(Person.canonical_name == "Bharat Mehta")
    ).one()
    with pytest.raises(ValueError, match="different candidacy"):
        attach_candidacy_source_identifier(
            session,
            candidacy=other_cnd,
            election=election,
            source_id=asha_cnd.source_id,
            external_value_raw="ECI-DEMO-CAND-001",
            source_system=SOURCE_SYSTEM_RESULTS,
        )


def test_affidavit_links_via_external_candidate_id(db_session) -> None:
    session, tmp_path = db_session
    from collectors.base.collector import CollectorContext
    from collectors.eci.affidavits.collector import EciAffidavitCollector
    from collectors.eci.affidavits.schemas import ParseOutcome
    from packages.db.models import Affidavit, SourceDocument

    _seed_election(session, tmp_path)
    ctx = CollectorContext(
        raw_root=tmp_path / "raw",
        failures_dir=tmp_path / "failures",
        git_commit_sha="identity-test-sha",
        git_dirty=False,
    )
    c = EciAffidavitCollector(ctx, session=session, fixture_path=AFFIDAVIT_FIXTURE)
    c.run()
    assert c._last_outcome in {ParseOutcome.SUCCESS, ParseOutcome.PARTIAL}
    aff = session.scalars(select(Affidavit)).one()
    assert aff.candidacy_id is not None
    src = session.get(SourceDocument, aff.source_id)
    assert src is not None
    assert src.extraction_confidence is None
    assert src.extraction_method == "plaintext"


def test_pdf_extraction_confidence_null(db_session) -> None:
    session, tmp_path = db_session
    from collectors.base.collector import CollectorContext
    from collectors.eci.affidavits.collector import EciAffidavitCollector
    from packages.db.models import Affidavit, SourceDocument

    _seed_election(session, tmp_path)
    ctx = CollectorContext(
        raw_root=tmp_path / "raw",
        failures_dir=tmp_path / "failures",
        git_commit_sha="identity-test-sha",
        git_dirty=False,
    )
    EciAffidavitCollector(ctx, session=session, fixture_path=PDF_FIXTURE).run()
    aff = session.scalars(select(Affidavit)).one()
    src = session.get(SourceDocument, aff.source_id)
    assert src is not None
    assert src.extraction_method == "pypdf"
    assert src.extraction_confidence is None


def test_ind_per_as_source_candidate_id_rejected(db_session) -> None:
    session, tmp_path = db_session
    from collectors.base.collector import CollectorContext
    from collectors.eci.affidavits.collector import EciAffidavitCollector
    from collectors.eci.affidavits.schemas import ParseOutcome
    from packages.db.models import Affidavit, Person

    _seed_election(session, tmp_path)
    person = session.scalars(select(Person).where(Person.canonical_name == "Asha Verma")).one()
    fixture = tmp_path / "bad_id.txt"
    text = AFFIDAVIT_FIXTURE.read_text(encoding="utf-8")
    text = text.replace("ECI-DEMO-CAND-001", person.person_id)
    # Also change name so only ID path would have worked under old bug
    text = text.replace("Asha Verma", "Unknown Candidate")
    fixture.write_text(text, encoding="utf-8")
    ctx = CollectorContext(
        raw_root=tmp_path / "raw",
        failures_dir=tmp_path / "failures",
        git_commit_sha="identity-test-sha",
        git_dirty=False,
    )
    c = EciAffidavitCollector(ctx, session=session, fixture_path=fixture)
    c.run()
    assert c._last_outcome == ParseOutcome.IDENTITY_REVIEW_REQUIRED
    assert session.scalar(select(func.count()).select_from(Affidavit)) == 0
