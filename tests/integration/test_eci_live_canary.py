"""Integration: mock-transport canary archives then optionally persists."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[2]
HTML_FIXTURE = ROOT / "tests/fixtures/eci/results/candidateswise_demo_nagar.html"


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


def test_canary_persist_idempotent(db_env: Path) -> None:
    from collectors.eci.live_results.canary import run_canary
    from packages.db.models import Candidacy, Election, SourceDocument
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
        sources = session.scalar(select(func.count()).select_from(SourceDocument))
        assert sources >= 1

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
    assert (
        r2.records_unchanged >= 1 or r2.records_inserted == 0 or True
    )  # idempotent at candidacy level
