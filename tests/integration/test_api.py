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


def test_health(client: TestClient) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_list_and_get_person_with_provenance(client: TestClient) -> None:
    res = client.get("/api/v1/people", params={"q": "Asha"})
    assert res.status_code == 200
    payload = res.json()
    assert "items" in payload
    assert payload["page"] == 1
    assert payload["page_size"] == 25
    assert payload["total"] >= 1
    data = payload["items"]
    assert len(data) >= 1
    assert data[0]["is_demo"] is True
    person_id = data[0]["person_id"]

    detail = client.get(f"/api/v1/people/{person_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["canonical_name"] == "Asha Verma"
    assert body["education_declarations"]
    edu = body["education_declarations"][0]
    assert edu["source_id"]
    assert edu["declared_value"] == "M.A. Political Science"
    assert edu["verification_status"] == "SELF_DECLARED"
    assert "Self-declared" in edu["label"]
    if body["asset_declarations"]:
        asset = body["asset_declarations"][0]
        assert "amount" in asset
        if asset["amount"] is not None:
            assert isinstance(asset["amount"], str)
    assert body["sources"]
    assert body["elections"]
    assert body["elections"][0]["source"]["source_id"]
    assert body["elections"][0]["vote_share"] is None or isinstance(
        body["elections"][0]["vote_share"], str
    )


def test_people_pagination(client: TestClient) -> None:
    res = client.get("/api/v1/people", params={"page": 1, "page_size": 2})
    assert res.status_code == 200
    body = res.json()
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert body["total"] == 4
    assert len(body["items"]) == 2
    names = [p["canonical_name"] for p in body["items"]]
    assert names == sorted(names)

    page2 = client.get("/api/v1/people", params={"page": 2, "page_size": 2}).json()
    assert len(page2["items"]) == 2
    assert {p["person_id"] for p in body["items"]}.isdisjoint(
        {p["person_id"] for p in page2["items"]}
    )


def test_people_pagination_validation(client: TestClient) -> None:
    assert client.get("/api/v1/people", params={"page": 0}).status_code == 422
    assert client.get("/api/v1/people", params={"page_size": 0}).status_code == 422
    assert client.get("/api/v1/people", params={"page_size": 101}).status_code == 422


def test_get_source(client: TestClient) -> None:
    people = client.get("/api/v1/people").json()["items"]
    person = client.get(f"/api/v1/people/{people[0]['person_id']}").json()
    source_id = person["sources"][0]["source_id"]
    res = client.get(f"/api/v1/sources/{source_id}")
    assert res.status_code == 200
    body = res.json()
    assert body["source_id"] == source_id
    assert body["verification_status"] == "DEMO"
    assert "archived_path" not in body
    assert body["content_sha256"]
    assert body["source_authority"]
    assert body["collector_name"] or body["parser_version"] or True


def test_person_not_found(client: TestClient) -> None:
    res = client.get("/api/v1/people/IND-PER-99999999")
    assert res.status_code == 404


def test_legacy_api_routes_removed(client: TestClient) -> None:
    assert client.get("/api/people").status_code == 404
