"""Offline tests for the guarded ECI live-results HTTP client and canary."""

from __future__ import annotations

import time
from pathlib import Path

import httpx
import pytest
from collectors.eci.live_results.canary import load_canary_config
from collectors.eci.live_results.http_client import (
    MAX_LIVE_REQUESTS,
    EciResultsHttpClient,
    LiveAccessError,
    LiveNetworkError,
    RequestBudget,
    assert_live_enabled,
    validate_eci_url,
)
from collectors.eci.live_results.parser import LayoutStatus, parse_candidateswise_html

ROOT = Path(__file__).resolve().parents[2]
HTML_FIXTURE = ROOT / "tests/fixtures/eci/results/candidateswise_demo_nagar.html"
CANARY_CONFIG = ROOT / "collectors/eci/live_results/canary_urls.yaml"


def test_live_disabled_by_default() -> None:
    from packages.shared.config import Settings

    assert Settings().eci_live_enabled is False
    with pytest.raises(LiveAccessError):
        assert_live_enabled(False)


def test_url_policy() -> None:
    validate_eci_url("https://results.eci.gov.in/PcResultGenJune2024/index.htm")
    with pytest.raises(LiveAccessError):
        validate_eci_url("http://results.eci.gov.in/x")
    with pytest.raises(LiveAccessError):
        validate_eci_url("https://example.com/x")
    with pytest.raises(LiveAccessError):
        validate_eci_url("https://1.2.3.4/x")


def test_request_cap_enforced() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>Election Commission of India candidate won</html>")

    transport = httpx.MockTransport(handler)
    budget = RequestBudget(max_requests=2, min_interval_seconds=0)
    with EciResultsHttpClient(transport=transport, budget=budget) as client:
        client.get("https://results.eci.gov.in/a.htm")
        client.get("https://results.eci.gov.in/b.htm")
        with pytest.raises(LiveNetworkError, match="request cap"):
            client.get("https://results.eci.gov.in/c.htm")
    assert budget.requests_made == 2
    assert MAX_LIVE_REQUESTS == 5


def test_min_delay_between_requests() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="ok")

    transport = httpx.MockTransport(handler)
    budget = RequestBudget(max_requests=3, min_interval_seconds=0.2)
    with EciResultsHttpClient(transport=transport, budget=budget) as client:
        t0 = time.monotonic()
        client.get("https://results.eci.gov.in/a.htm")
        client.get("https://results.eci.gov.in/b.htm")
        elapsed = time.monotonic() - t0
    assert elapsed >= 0.2
    assert budget.spacings[0] >= 0.2


def test_403_stops() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="forbidden")

    with EciResultsHttpClient(
        transport=httpx.MockTransport(handler), budget=RequestBudget(min_interval_seconds=0)
    ) as client:
        with pytest.raises(LiveNetworkError, match="403"):
            client.get("https://results.eci.gov.in/x.htm")


def test_429_stops() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "120"}, text="slow down")

    with EciResultsHttpClient(
        transport=httpx.MockTransport(handler), budget=RequestBudget(min_interval_seconds=0)
    ) as client:
        with pytest.raises(LiveNetworkError, match="429"):
            client.get("https://results.eci.gov.in/x.htm")


def test_response_size_cap() -> None:
    from collectors.eci.live_results.http_client import MAX_RESPONSE_BYTES

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * (MAX_RESPONSE_BYTES + 1))

    with EciResultsHttpClient(
        transport=httpx.MockTransport(handler), budget=RequestBudget(min_interval_seconds=0)
    ) as client:
        with pytest.raises(LiveNetworkError, match="size cap"):
            client.get("https://results.eci.gov.in/big.htm")


def test_redirect_outside_allowlist_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/start"):
            return httpx.Response(302, headers={"Location": "https://evil.example/x"})
        return httpx.Response(200, text="ok")

    with EciResultsHttpClient(
        transport=httpx.MockTransport(handler), budget=RequestBudget(min_interval_seconds=0)
    ) as client:
        with pytest.raises(LiveAccessError):
            client.get("https://results.eci.gov.in/start")


def test_html_fixture_parses() -> None:
    html = HTML_FIXTURE.read_text(encoding="utf-8")
    layout, parsed = parse_candidateswise_html(html)
    assert layout.status == LayoutStatus.OK
    assert parsed is not None
    assert parsed.constituency.name == "Demo Nagar"
    assert len(parsed.candidates) == 3
    assert parsed.candidates[0].result == "WON"
    assert all(c.source_candidate_id is None for c in parsed.candidates)


def test_layout_change_fail_closed() -> None:
    layout, parsed = parse_candidateswise_html("<html><body>unrelated</body></html>")
    assert layout.status == LayoutStatus.LAYOUT_CHANGED
    assert parsed is None


def test_canary_config_urls_validated() -> None:
    cfg = load_canary_config(CANARY_CONFIG)
    assert cfg["election_year"] == 2024
    assert all(u.startswith("https://results.eci.gov.in/") for u in cfg["urls"])


def test_canary_requires_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MPTA_ECI_LIVE_ENABLED", "false")
    from packages.shared.config import get_settings

    get_settings.cache_clear()
    with pytest.raises(LiveAccessError):
        assert_live_enabled(get_settings().eci_live_enabled)
    get_settings.cache_clear()


def test_archive_live_response_helper(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    from collectors.base.collector import CollectorContext, RunStats
    from collectors.eci.live_results.canary import _archive_live_response
    from collectors.eci.live_results.http_client import LiveResponse

    html = HTML_FIXTURE.read_text(encoding="utf-8").encode()
    ctx = CollectorContext(
        raw_root=tmp_path / "raw",
        failures_dir=tmp_path / "failures",
        git_commit_sha="test",
        git_dirty=False,
    )
    live = LiveResponse(
        url="https://results.eci.gov.in/demo.htm",
        final_url="https://results.eci.gov.in/demo.htm",
        status_code=200,
        content=html,
        content_type="text/html",
        retrieved_at=datetime.now(UTC),
    )
    archived = _archive_live_response(ctx, live, RunStats())
    assert archived.payload_path.is_file()
    assert archived.sha256
    layout, parsed = parse_candidateswise_html(archived.payload_path.read_text(encoding="utf-8"))
    assert layout.status == LayoutStatus.OK
    assert parsed is not None
