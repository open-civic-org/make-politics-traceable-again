"""Integration: mock-transport canary archives then optionally persists."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[2]
HTML_FIXTURE = ROOT / "tests/fixtures/eci/results/candidateswise_demo_nagar.html"
ELECTION_FIXTURE = ROOT / "tests/fixtures/eci/election_results/ge2024_demo_nagar.json"


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
def db_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    url, handle = _fresh_db()
    previous = os.environ.get("DATABASE_URL")
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("MPTA_ECI_LIVE_ENABLED", "true")
    monkeypatch.setenv("MPTA_GIT_COMMIT_SHA", "canary-test-sha")

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
    yield tmp_path
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    get_settings.cache_clear()
    if previous is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = previous
    if handle is not None:
        del handle


def test_canary_capture_only_archives(db_env: Path) -> None:
    from collectors.eci.live_results.canary import run_canary
    from collectors.eci.live_results.parser import LayoutStatus

    html = HTML_FIXTURE.read_text(encoding="utf-8")
    cfg = db_env / "canary.yaml"
    cfg.write_text(
        "canary:\n  election_type: LOK_SABHA\n  election_year: 2024\n  urls:\n"
        "    - https://results.eci.gov.in/PcResultGenJune2024/candidateswise-demo.htm\n",
        encoding="utf-8",
    )

    report = run_canary(
        config_path=cfg,
        confirm_live=True,
        capture_only=True,
        raw_root=db_env / "raw",
        failures_dir=db_env / "failures",
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, text=html, headers={"content-type": "text/html"})
        ),
    )
    assert report.request_count == 1
    assert report.results[0].sha256
    assert Path(report.results[0].archive_path).exists()
    assert report.layout_status == LayoutStatus.OK.value
    assert report.persist_attempted is False
    assert report.robots_preflight is None
    assert report.as_dict()["robots_preflight"] == "NOT_RUN"


def test_canary_persist_idempotent_and_live_provenance(db_env: Path) -> None:
    from collectors.eci.live_results.canary import COLLECTOR_NAME, COLLECTOR_VERSION, run_canary
    from collectors.eci.live_results.parser import PARSER_VERSION
    from packages.db.models import Candidacy, Election, ElectionResult, SourceDocument
    from packages.db.session import get_session_factory

    html = HTML_FIXTURE.read_text(encoding="utf-8")
    cfg = db_env / "canary.yaml"
    cfg.write_text(
        "canary:\n  election_type: LOK_SABHA\n  election_year: 2024\n  urls:\n"
        "    - https://results.eci.gov.in/PcResultGenJune2024/candidateswise-demo.htm\n",
        encoding="utf-8",
    )
    transport = httpx.MockTransport(
        lambda r: httpx.Response(200, text=html, headers={"content-type": "text/html"})
    )
    r1 = run_canary(
        config_path=cfg,
        confirm_live=True,
        capture_only=False,
        persist=True,
        raw_root=db_env / "raw",
        failures_dir=db_env / "failures",
        transport=transport,
    )
    assert r1.persist_attempted is True
    assert r1.records_valid == 3

    Session = get_session_factory()
    with Session() as session:
        assert session.scalar(select(func.count()).select_from(Election)) == 1
        assert session.scalar(select(func.count()).select_from(Candidacy)) == 3
        src = session.scalars(select(SourceDocument)).one()
        assert src.collector_name == COLLECTOR_NAME
        assert src.collector_version == COLLECTOR_VERSION
        assert src.parser_version == PARSER_VERSION
        assert src.extraction_method == "archived_html"
        assert src.extraction_confidence is None
        for res in session.scalars(select(ElectionResult)).all():
            assert res.rank is None

    r2 = run_canary(
        config_path=cfg,
        confirm_live=True,
        capture_only=False,
        persist=True,
        raw_root=db_env / "raw",
        failures_dir=db_env / "failures",
        transport=transport,
    )
    with Session() as session:
        assert session.scalar(select(func.count()).select_from(Candidacy)) == 3
        assert session.scalar(select(func.count()).select_from(SourceDocument)) == 1
    assert r2.records_unchanged >= 1


def test_source_changed_does_not_mutate_canonical_result(db_env: Path) -> None:
    from collectors.base.archive import archive_raw, build_raw_from_bytes
    from collectors.base.collector import RunStats
    from collectors.eci.normalize import normalize_election
    from collectors.eci.parser import parse_eci_result_json
    from collectors.eci.persist import (
        FIXTURE_PARSER_VERSION,
        fixture_election_provenance,
        persist_normalized_election,
    )
    from collectors.eci.validation import validate_election
    from packages.db.models import ElectionResult, ReviewItem, SourceDocument
    from packages.db.session import get_session_factory

    data = json.loads(ELECTION_FIXTURE.read_text(encoding="utf-8"))
    url = "https://results.eci.gov.in/historical/demo-nagar.htm"
    Session = get_session_factory()
    with Session() as session:
        raw_a = build_raw_from_bytes(
            source_name="eci",
            source_url=url,
            payload=json.dumps(data).encode(),
            collector_version="0.1.0",
            git_commit_sha="sha-a",
            retrieved_at=datetime.now(UTC),
            content_type="application/json",
        )
        arch_a = archive_raw(raw_a, raw_root=db_env / "raw", category="election_results", year=2024)
        parsed = parse_eci_result_json(data)
        validated = validate_election(normalize_election(parsed))
        status_a = persist_normalized_election(
            session,
            validated,
            arch_a,
            RunStats(),
            provenance=fixture_election_provenance(collector_version="0.1.0"),
        )
        assert status_a == "INSERTED"
        session.commit()

        original = session.scalars(
            select(ElectionResult).where(ElectionResult.votes_received == 612345)
        ).one()
        original_votes = original.votes_received
        original_result_id = original.result_id

        data_b = json.loads(json.dumps(data))
        data_b["candidates"][0]["votes"] = 999999
        raw_b = build_raw_from_bytes(
            source_name="eci",
            source_url=url,
            payload=json.dumps(data_b).encode(),
            collector_version="0.1.0",
            git_commit_sha="sha-b",
            retrieved_at=datetime.now(UTC),
            content_type="application/json",
        )
        arch_b = archive_raw(raw_b, raw_root=db_env / "raw", category="election_results", year=2024)
        parsed_b = parse_eci_result_json(data_b)
        validated_b = validate_election(normalize_election(parsed_b))
        status_b = persist_normalized_election(
            session,
            validated_b,
            arch_b,
            RunStats(),
            provenance=fixture_election_provenance(collector_version="0.1.0"),
        )
        assert status_b == "SOURCE_CHANGED"
        session.commit()

        unchanged = session.get(ElectionResult, original_result_id)
        assert unchanged is not None
        assert unchanged.votes_received == original_votes
        assert unchanged.votes_received != 999999

        sources = session.scalars(
            select(SourceDocument).where(SourceDocument.source_url == url)
        ).all()
        assert len(sources) == 2
        assert {s.content_sha256 for s in sources} == {arch_a.sha256, arch_b.sha256}

        reviews = session.scalars(
            select(ReviewItem).where(ReviewItem.review_type == "DOCUMENT_REVIEW_REQUIRED")
        ).all()
        assert len(reviews) >= 1
        assert any("SOURCE_CHANGED" in r.reason for r in reviews)
        assert any(r.parser_version == FIXTURE_PARSER_VERSION for r in reviews)


def test_fixture_pipeline_provenance(db_env: Path) -> None:
    from collectors.base.collector import CollectorContext
    from collectors.eci.collector import EciElectionResultsCollector
    from collectors.eci.persist import FIXTURE_PARSER_VERSION
    from packages.db.models import SourceDocument
    from packages.db.session import get_session_factory

    Session = get_session_factory()
    with Session() as session:
        ctx = CollectorContext(
            raw_root=db_env / "raw",
            failures_dir=db_env / "failures",
            git_commit_sha="fixture-prov",
            git_dirty=False,
        )
        EciElectionResultsCollector(ctx, session=session, fixture_path=ELECTION_FIXTURE).run()
        src = session.scalars(select(SourceDocument)).one()
        assert src.collector_name == "eci_election_results"
        assert src.parser_version == FIXTURE_PARSER_VERSION
        assert src.extraction_method == "fixture_json"
        assert src.extraction_confidence is None
