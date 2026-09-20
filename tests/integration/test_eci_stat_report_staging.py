"""Integration tests for ECI Statistical Report 33 staging (no canonical mutation)."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/eci/statistical_reports/report33/report33_schema_fixture.xls"
ELECTION_FIXTURE = ROOT / "tests/fixtures/eci/election_results/ge2024_demo_nagar.json"


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
    os.environ["MPTA_GIT_COMMIT_SHA"] = "stat-report-test-sha"

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
        raw_root=tmp_path / "raw_election",
        failures_dir=tmp_path / "failures",
        git_commit_sha="stat-report-test-sha",
        git_dirty=False,
    )
    collector = EciElectionResultsCollector(ctx, session=session, fixture_path=ELECTION_FIXTURE)
    collector.run()
    session.commit()


def test_fixture_import_stages_without_canonical_growth(db_session) -> None:
    session, tmp_path = db_session
    from collectors.eci.statistical_reports.schemas import PARSER_VERSION
    from collectors.eci.statistical_reports.staging import import_fixture_path
    from packages.db.models import (
        Candidacy,
        EciElectionResultSourceRecord,
        ElectionResult,
        Person,
        SourceDocument,
    )

    people_before = session.scalar(select(func.count()).select_from(Person)) or 0
    cand_before = session.scalar(select(func.count()).select_from(Candidacy)) or 0
    res_before = session.scalar(select(func.count()).select_from(ElectionResult)) or 0

    summary = import_fixture_path(
        session,
        FIXTURE,
        raw_root=tmp_path / "raw",
        dry_run=False,
        git_commit_sha="stat-report-test-sha",
    )
    session.commit()

    assert summary.source_status == "INSERTED"
    assert summary.rows_inserted == 6
    assert summary.rows_total == 6
    assert summary.schema_status == "SCHEMA_MATCH"
    assert summary.parser_version == PARSER_VERSION

    staged = session.scalars(select(EciElectionResultSourceRecord)).all()
    assert len(staged) == 6
    assert all(r.result_normalized == "UNKNOWN" for r in staged)
    assert all(r.rank is None for r in staged)
    assert all(r.parser_version == PARSER_VERSION for r in staged)

    src = session.get(SourceDocument, summary.source_id)
    assert src is not None
    assert src.extraction_method == "archived_workbook"
    assert src.extraction_confidence is None
    assert src.parser_version == PARSER_VERSION
    assert src.collector_name == "eci_statistical_reports"
    assert src.git_commit_sha == "stat-report-test-sha"

    assert session.scalar(select(func.count()).select_from(Person)) == people_before
    assert session.scalar(select(func.count()).select_from(Candidacy)) == cand_before
    assert session.scalar(select(func.count()).select_from(ElectionResult)) == res_before


def test_idempotent_second_import(db_session) -> None:
    session, tmp_path = db_session
    from collectors.eci.statistical_reports.staging import import_fixture_path
    from packages.db.models import EciElectionResultSourceRecord, SourceDocument

    raw_root = tmp_path / "raw"
    s1 = import_fixture_path(session, FIXTURE, raw_root=raw_root, git_commit_sha="sha")
    session.commit()
    s2 = import_fixture_path(session, FIXTURE, raw_root=raw_root, git_commit_sha="sha")
    session.commit()

    assert s1.source_status == "INSERTED"
    assert s2.source_status == "UNCHANGED"
    assert s2.rows_inserted == 0
    assert s2.rows_skipped == 6
    assert session.scalar(select(func.count()).select_from(EciElectionResultSourceRecord)) == 6
    assert session.scalar(select(func.count()).select_from(SourceDocument)) == 1


def test_source_changed_retains_old_staging(db_session) -> None:
    session, tmp_path = db_session
    import xlrd
    import xlwt
    from collectors.eci.statistical_reports.staging import import_workbook_bytes
    from packages.db.models import EciElectionResultSourceRecord, ReviewItem, SourceDocument

    url = "fixture://eci/statistical_reports/report33/changed.xls"
    raw_root = tmp_path / "raw"

    original = FIXTURE.read_bytes()
    s1 = import_workbook_bytes(
        session, original, source_url=url, raw_root=raw_root, git_commit_sha="sha1"
    )
    session.commit()
    assert s1.source_status == "INSERTED"
    old_count = session.scalar(select(func.count()).select_from(EciElectionResultSourceRecord))
    assert old_count == 6

    # Build a workbook with same schema but different votes for Asha Verma.
    book = xlrd.open_workbook(file_contents=original)
    sh = book.sheet_by_index(0)
    out = xlwt.Workbook()
    ws = out.add_sheet(sh.name)
    for r in range(sh.nrows):
        for c in range(sh.ncols):
            val = sh.cell_value(r, c)
            if r == 1 and c == 12:  # Votes Secured - Total
                val = 999999.0
            ws.write(r, c, val)
    buf = tempfile.NamedTemporaryFile(suffix=".xls", delete=False)
    try:
        out.save(buf.name)
        changed = Path(buf.name).read_bytes()
    finally:
        Path(buf.name).unlink(missing_ok=True)

    assert hashlib.sha256(changed).hexdigest() != hashlib.sha256(original).hexdigest()

    s2 = import_workbook_bytes(
        session, changed, source_url=url, raw_root=raw_root, git_commit_sha="sha2"
    )
    session.commit()
    assert s2.source_status == "SOURCE_CHANGED"
    assert s2.rows_inserted == 6

    # Old + new staging rows retained under different source_ids.
    assert session.scalar(select(func.count()).select_from(EciElectionResultSourceRecord)) == 12
    assert session.scalar(select(func.count()).select_from(SourceDocument)) == 2

    reviews = session.scalars(
        select(ReviewItem).where(ReviewItem.review_type == "DOCUMENT_REVIEW_REQUIRED")
    ).all()
    assert any("SOURCE_CHANGED" in r.reason for r in reviews)

    # New votes visible on the new source only.
    new_rows = session.scalars(
        select(EciElectionResultSourceRecord).where(
            EciElectionResultSourceRecord.source_id == s2.source_id,
            EciElectionResultSourceRecord.candidate_name_normalized == "asha verma",
        )
    ).all()
    assert len(new_rows) == 1
    assert new_rows[0].votes_value == 999999


def test_identity_exact_linked_with_seed_election(db_session) -> None:
    session, tmp_path = db_session
    from collectors.eci.statistical_reports.staging import import_fixture_path
    from packages.db.models import (
        Candidacy,
        EciElectionResultSourceRecord,
        ElectionResult,
        Person,
    )

    _seed_election(session, tmp_path)
    people = session.scalar(select(func.count()).select_from(Person))
    cands = session.scalar(select(func.count()).select_from(Candidacy))
    results = session.scalar(select(func.count()).select_from(ElectionResult))

    summary = import_fixture_path(
        session,
        FIXTURE,
        raw_root=tmp_path / "raw_stat",
        git_commit_sha="stat-report-test-sha",
    )
    session.commit()

    asha = session.scalars(
        select(EciElectionResultSourceRecord).where(
            EciElectionResultSourceRecord.candidate_name_normalized == "asha verma"
        )
    ).one()
    assert asha.identity_status == "EXACT_LINKED"
    assert asha.identity_candidacy_id is not None

    # Canonical tables unchanged by statistical import.
    assert session.scalar(select(func.count()).select_from(Person)) == people
    assert session.scalar(select(func.count()).select_from(Candidacy)) == cands
    assert session.scalar(select(func.count()).select_from(ElectionResult)) == results
    assert summary.identity_counts.get("EXACT_LINKED", 0) >= 1


def test_identity_unresolved_and_ambiguous(db_session) -> None:
    session, tmp_path = db_session
    from collectors.eci.statistical_reports.staging import import_fixture_path
    from packages.db.models import (
        Candidacy,
        EciElectionResultSourceRecord,
        Election,
        ParliamentaryConstituency,
        Person,
    )
    from packages.shared.ids import IdPrefix, allocate_id, normalize_name

    _seed_election(session, tmp_path)

    # Create a second candidacy for "Deepak Singh" under a second PC also named Demo Pur
    # is hard; instead duplicate Asha Verma under another election with same PC name
    # by cloning constituency+election+candidacy for AMBIGUOUS on Asha.
    asha = session.scalars(select(Person).where(Person.canonical_name == "Asha Verma")).one()
    existing_cnd = session.scalars(
        select(Candidacy).where(Candidacy.person_id == asha.person_id)
    ).one()
    existing_elc = session.get(Election, existing_cnd.election_id)
    assert existing_elc is not None

    # Second PC with same display name "Demo Nagar" in another state id path — same
    # normalized constituency name so reconcile sees >1 match.
    from packages.db.models import SourceDocument, State

    src = session.scalars(select(SourceDocument)).first()
    assert src is not None
    state2 = State(
        state_id=allocate_id(IdPrefix.STATE, 900),
        name="Rajasthan Twin",
        code="RJ2",
        source_id=src.source_id,
    )
    session.add(state2)
    session.flush()
    pc2 = ParliamentaryConstituency(
        pc_id=allocate_id(IdPrefix.PC, 900),
        state_id=state2.state_id,
        name="Demo Nagar",
        eci_code="DEMO-NAGAR-2",
        source_id=src.source_id,
    )
    session.add(pc2)
    session.flush()
    elc2 = Election(
        election_id=allocate_id(IdPrefix.ELECTION, 900),
        election_type="LOK_SABHA",
        year=2024,
        election_date=existing_elc.election_date,
        state_id=state2.state_id,
        constituency_pc_id=pc2.pc_id,
        source_id=src.source_id,
    )
    session.add(elc2)
    session.flush()
    cnd2 = Candidacy(
        candidacy_id=allocate_id(IdPrefix.CANDIDACY, 900),
        person_id=asha.person_id,
        election_id=elc2.election_id,
        party_id=existing_cnd.party_id,
        candidate_name_as_published="Asha Verma",
        nomination_status="ACCEPTED",
        source_id=src.source_id,
    )
    session.add(cnd2)
    session.commit()

    import_fixture_path(
        session,
        FIXTURE,
        raw_root=tmp_path / "raw_stat",
        git_commit_sha="stat-report-test-sha",
    )
    session.commit()

    asha_row = session.scalars(
        select(EciElectionResultSourceRecord).where(
            EciElectionResultSourceRecord.candidate_name_normalized == normalize_name("Asha Verma")
        )
    ).one()
    assert asha_row.identity_status == "AMBIGUOUS"
    assert asha_row.identity_candidacy_id is None

    # Deepak Singh has no seeded candidacy → UNRESOLVED
    deepak = session.scalars(
        select(EciElectionResultSourceRecord).where(
            EciElectionResultSourceRecord.candidate_name_normalized
            == normalize_name("Deepak Singh")
        )
    ).one()
    assert deepak.identity_status == "UNRESOLVED"


def test_extraction_confidence_null_and_parser_preserved(db_session) -> None:
    session, tmp_path = db_session
    from collectors.eci.statistical_reports.schemas import PARSER_VERSION
    from collectors.eci.statistical_reports.staging import import_fixture_path
    from packages.db.models import EciElectionResultSourceRecord, SourceDocument

    summary = import_fixture_path(
        session, FIXTURE, raw_root=tmp_path / "raw", git_commit_sha="stat-report-test-sha"
    )
    session.commit()
    src = session.get(SourceDocument, summary.source_id)
    assert src is not None
    assert src.extraction_confidence is None
    assert src.parser_version == PARSER_VERSION
    row = session.scalars(select(EciElectionResultSourceRecord)).first()
    assert row is not None
    assert row.parser_version == PARSER_VERSION
