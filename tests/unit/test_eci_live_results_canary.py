"""Offline tests for the guarded ECI live-results HTTP client and canary."""

from __future__ import annotations

import time
from pathlib import Path

import httpx
import pytest
from collectors.eci.live_results.canary import load_canary_config
from collectors.eci.live_results.http_client import (
    MAX_LIVE_REQUESTS,
    MAX_RESPONSE_BYTES,
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
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, text="<html>Election Commission of India candidate won</html>")

    budget = RequestBudget(max_requests=2, min_interval_seconds=0)
    with EciResultsHttpClient(transport=httpx.MockTransport(handler), budget=budget) as client:
        client.get("https://results.eci.gov.in/a.htm")
        client.get("https://results.eci.gov.in/b.htm")
        with pytest.raises(LiveNetworkError, match="request cap"):
            client.get("https://results.eci.gov.in/c.htm")
    assert budget.requests_made == 2
    assert calls["n"] == 2
    assert MAX_LIVE_REQUESTS == 5


def test_min_delay_between_requests() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="ok")

    budget = RequestBudget(max_requests=3, min_interval_seconds=0.2)
    with EciResultsHttpClient(transport=httpx.MockTransport(handler), budget=budget) as client:
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


def test_relative_redirect_allowlisted() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/start"):
            return httpx.Response(302, headers={"Location": "/next.htm"})
        return httpx.Response(200, text="ok-body")

    budget = RequestBudget(max_requests=5, min_interval_seconds=0)
    with EciResultsHttpClient(transport=httpx.MockTransport(handler), budget=budget) as client:
        live = client.get("https://results.eci.gov.in/start")
    assert live.status_code == 200
    assert live.final_url == "https://results.eci.gov.in/next.htm"
    assert live.content == b"ok-body"
    assert budget.requests_made == 2


def test_absolute_redirect_allowlisted() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/start"):
            return httpx.Response(302, headers={"Location": "https://results.eci.gov.in/dest.htm"})
        return httpx.Response(200, text="dest")

    budget = RequestBudget(min_interval_seconds=0)
    with EciResultsHttpClient(transport=httpx.MockTransport(handler), budget=budget) as client:
        live = client.get("https://results.eci.gov.in/start")
    assert live.final_url.endswith("/dest.htm")
    assert budget.requests_made == 2


def test_redirect_to_non_eci_sends_zero_external_requests() -> None:
    hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host or "")
        if request.url.host == "evil.example":
            return httpx.Response(200, text="leaked")
        return httpx.Response(302, headers={"Location": "https://evil.example/x"})

    with EciResultsHttpClient(
        transport=httpx.MockTransport(handler), budget=RequestBudget(min_interval_seconds=0)
    ) as client:
        with pytest.raises(LiveAccessError, match="allowlisted"):
            client.get("https://results.eci.gov.in/start")
    assert hosts == ["results.eci.gov.in"]
    assert "evil.example" not in hosts


def test_redirect_to_http_rejected_before_request() -> None:
    hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hosts.append(str(request.url))
        return httpx.Response(302, headers={"Location": "http://results.eci.gov.in/x"})

    with EciResultsHttpClient(
        transport=httpx.MockTransport(handler), budget=RequestBudget(min_interval_seconds=0)
    ) as client:
        with pytest.raises(LiveAccessError, match="HTTPS"):
            client.get("https://results.eci.gov.in/start")
    assert len(hosts) == 1
    assert hosts[0].startswith("https://")


def test_redirect_to_ip_literal_rejected_before_request() -> None:
    hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host or "")
        return httpx.Response(302, headers={"Location": "https://1.2.3.4/x"})

    with EciResultsHttpClient(
        transport=httpx.MockTransport(handler), budget=RequestBudget(min_interval_seconds=0)
    ) as client:
        with pytest.raises(LiveAccessError, match="IP-literal"):
            client.get("https://results.eci.gov.in/start")
    assert hosts == ["results.eci.gov.in"]


def test_redirect_loop_bounded() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/a"):
            return httpx.Response(302, headers={"Location": "/b"})
        return httpx.Response(302, headers={"Location": "/a"})

    with EciResultsHttpClient(
        transport=httpx.MockTransport(handler), budget=RequestBudget(min_interval_seconds=0)
    ) as client:
        with pytest.raises(LiveNetworkError, match="redirect loop"):
            client.get("https://results.eci.gov.in/a")


def test_redirect_hop_count_bounded() -> None:
    from collectors.eci.live_results.http_client import MAX_REDIRECT_HOPS

    def handler(request: httpx.Request) -> httpx.Response:
        n = int(request.url.path.strip("/") or "0")
        return httpx.Response(302, headers={"Location": f"/{n + 1}"})

    budget = RequestBudget(max_requests=20, min_interval_seconds=0)
    with EciResultsHttpClient(transport=httpx.MockTransport(handler), budget=budget) as client:
        with pytest.raises(LiveNetworkError, match="hop limit"):
            client.get("https://results.eci.gov.in/0")
    # initial + MAX_REDIRECT_HOPS redirect responses, each consumed budget before hop check
    assert budget.requests_made == MAX_REDIRECT_HOPS + 1


def test_5xx_retries_consume_budget() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, text="busy")

    budget = RequestBudget(max_requests=5, min_interval_seconds=0)
    with EciResultsHttpClient(transport=httpx.MockTransport(handler), budget=budget) as client:
        with pytest.raises(LiveNetworkError, match="503"):
            client.get("https://results.eci.gov.in/x.htm")
    # 1 initial + 2 retries = 3
    assert calls["n"] == 3
    assert budget.requests_made == 3


def test_timeout_retries_consume_budget() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.ReadTimeout("slow", request=request)

    budget = RequestBudget(max_requests=5, min_interval_seconds=0)
    with EciResultsHttpClient(transport=httpx.MockTransport(handler), budget=budget) as client:
        with pytest.raises(LiveNetworkError, match="timeout"):
            client.get("https://results.eci.gov.in/x.htm")
    assert calls["n"] == 3
    assert budget.requests_made == 3


def test_retries_cannot_exceed_max_live_requests() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, text="busy")

    budget = RequestBudget(max_requests=2, min_interval_seconds=0)
    with EciResultsHttpClient(transport=httpx.MockTransport(handler), budget=budget) as client:
        with pytest.raises(LiveNetworkError, match="request cap"):
            client.get("https://results.eci.gov.in/x.htm")
    assert calls["n"] == 2
    assert budget.requests_made == 2


def test_retry_and_redirect_respect_spacing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/start"):
            return httpx.Response(302, headers={"Location": "/next"})
        return httpx.Response(200, text="ok")

    budget = RequestBudget(max_requests=5, min_interval_seconds=0.15)
    with EciResultsHttpClient(transport=httpx.MockTransport(handler), budget=budget) as client:
        t0 = time.monotonic()
        client.get("https://results.eci.gov.in/start")
        elapsed = time.monotonic() - t0
    assert budget.requests_made == 2
    assert elapsed >= 0.15
    assert all(s >= 0.15 for s in budget.spacings)


def test_oversized_content_length_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"tiny",
            headers={"Content-Length": str(MAX_RESPONSE_BYTES + 1)},
        )

    with EciResultsHttpClient(
        transport=httpx.MockTransport(handler), budget=RequestBudget(min_interval_seconds=0)
    ) as client:
        with pytest.raises(LiveNetworkError, match="Content-Length"):
            client.get("https://results.eci.gov.in/big.htm")


def test_chunked_body_crossing_size_limit_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # Omit Content-Length so the stream path enforces the cap incrementally.
        return httpx.Response(200, content=b"x" * (MAX_RESPONSE_BYTES + 100))

    with EciResultsHttpClient(
        transport=httpx.MockTransport(handler), budget=RequestBudget(min_interval_seconds=0)
    ) as client:
        with pytest.raises(LiveNetworkError, match="size cap"):
            client.get("https://results.eci.gov.in/big.htm")


def test_body_exactly_at_size_cap_accepted() -> None:
    body = b"y" * MAX_RESPONSE_BYTES

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=body, headers={"Content-Length": str(MAX_RESPONSE_BYTES)}
        )

    with EciResultsHttpClient(
        transport=httpx.MockTransport(handler), budget=RequestBudget(min_interval_seconds=0)
    ) as client:
        live = client.get("https://results.eci.gov.in/exact.htm")
    assert len(live.content) == MAX_RESPONSE_BYTES


def test_normal_small_response_accepted() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="small")

    with EciResultsHttpClient(
        transport=httpx.MockTransport(handler), budget=RequestBudget(min_interval_seconds=0)
    ) as client:
        live = client.get("https://results.eci.gov.in/small.htm")
    assert live.content == b"small"


def test_html_fixture_parses() -> None:
    html = HTML_FIXTURE.read_text(encoding="utf-8")
    layout, parsed = parse_candidateswise_html(html)
    assert layout.status == LayoutStatus.OK
    assert parsed is not None
    assert parsed.constituency.name == "Demo Nagar"
    assert parsed.constituency.state_name == "Rajasthan"
    assert len(parsed.candidates) == 3
    assert parsed.candidates[0].result == "WON"
    assert all(c.rank is None for c in parsed.candidates)
    assert all(c.source_candidate_id is None for c in parsed.candidates)


def test_layout_change_fail_closed() -> None:
    layout, parsed = parse_candidateswise_html("<html><body>unrelated</body></html>")
    assert layout.status == LayoutStatus.LAYOUT_CHANGED
    assert parsed is None


def test_unknown_geography_fail_closed() -> None:
    html = """<!DOCTYPE html><html><head><title>t</title></head><body>
    <h1>Election Commission of India</h1>
    <p>Form-20 Returning Officer</p>
    <div>won 100 (+1) Asha Verma People's Civic Front</div>
    </body></html>"""
    layout, parsed = parse_candidateswise_html(html)
    assert layout.status == LayoutStatus.LAYOUT_CHANGED
    assert parsed is None
    assert any("constituency" in r or "state" in r for r in layout.reasons)


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


def test_robots_preflight_not_fabricated() -> None:
    from collectors.eci.live_results.canary import CanaryReport

    report = CanaryReport()
    assert report.robots_preflight is None
    assert report.as_dict()["robots_preflight"] == "NOT_RUN"


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
