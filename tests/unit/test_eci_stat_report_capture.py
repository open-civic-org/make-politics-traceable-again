"""Offline tests for guarded ECI statistical-report capture."""

from __future__ import annotations

import time
from pathlib import Path

import httpx
import pytest
from collectors.eci.statistical_reports.capture import (
    CaptureReport,
    capture_report,
    detect_container_format,
)
from collectors.eci.statistical_reports.http_client import (
    ALLOWED_HOSTS,
    MAX_HTTP_ATTEMPTS,
    CaptureAccessError,
    CaptureNetworkError,
    EciStatisticalReportHttpClient,
    RequestBudget,
    assert_live_enabled,
    validate_capture_url,
)

OLE_XLS = b"\xd0\xcf\x11\xe0" + b"\x00" * 64
XLSX_ZIP = b"PK\x03\x04" + b"\x00" * 64
HTML_AS_XLS = b"<!DOCTYPE html><html><body>not a workbook</body></html>"


def test_live_disabled_by_default() -> None:
    from packages.shared.config import Settings

    assert Settings().eci_stat_report_live_enabled is False
    with pytest.raises(CaptureAccessError):
        assert_live_enabled(False)


def test_confirm_live_required(tmp_path: Path) -> None:
    report = capture_report(
        url="https://www.eci.gov.in/file.xls",
        report_number="33",
        report_title="Constituency Wise Detailed Result",
        election_year=2024,
        election_type="LOK_SABHA",
        confirm_live=False,
        live_enabled=True,
        raw_root=tmp_path,
    )
    assert report.outcome == "FAILED"
    assert "--confirm-live" in (report.error or "")


def test_url_policy() -> None:
    validate_capture_url("https://www.eci.gov.in/path/file.xls")
    validate_capture_url("https://eci.gov.in/path/file.xls")
    assert "results.eci.gov.in" not in ALLOWED_HOSTS
    with pytest.raises(CaptureAccessError):
        validate_capture_url("http://www.eci.gov.in/x")
    with pytest.raises(CaptureAccessError):
        validate_capture_url("https://example.com/x")
    with pytest.raises(CaptureAccessError):
        validate_capture_url("https://results.eci.gov.in/x")
    with pytest.raises(CaptureAccessError):
        validate_capture_url("https://1.2.3.4/x")
    with pytest.raises(CaptureAccessError):
        validate_capture_url("https://user:pass@www.eci.gov.in/x")
    with pytest.raises(CaptureAccessError):
        validate_capture_url("https://127.0.0.1/x")


def test_external_redirect_rejected_before_request() -> None:
    hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host or "")
        if request.url.host == "evil.example":
            return httpx.Response(200, content=OLE_XLS)
        return httpx.Response(302, headers={"Location": "https://evil.example/x"})

    with EciStatisticalReportHttpClient(
        transport=httpx.MockTransport(handler), budget=RequestBudget(min_interval_seconds=0)
    ) as client:
        with pytest.raises(CaptureAccessError, match="allowlisted"):
            client.get("https://www.eci.gov.in/start")
    assert hosts == ["www.eci.gov.in"]
    assert "evil.example" not in hosts


def test_allowed_redirect_works() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/start"):
            return httpx.Response(302, headers={"Location": "/final.xls"})
        return httpx.Response(
            200,
            content=OLE_XLS,
            headers={"content-type": "application/vnd.ms-excel"},
        )

    budget = RequestBudget(min_interval_seconds=0)
    with EciStatisticalReportHttpClient(
        transport=httpx.MockTransport(handler), budget=budget
    ) as client:
        live = client.get("https://www.eci.gov.in/start")
    assert live.status_code == 200
    assert live.final_url.endswith("/final.xls")
    assert budget.requests_made == 2


def test_redirect_loop_bounded() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/a"):
            return httpx.Response(302, headers={"Location": "/b"})
        return httpx.Response(302, headers={"Location": "/a"})

    with EciStatisticalReportHttpClient(
        transport=httpx.MockTransport(handler), budget=RequestBudget(min_interval_seconds=0)
    ) as client:
        with pytest.raises(CaptureNetworkError, match="redirect loop"):
            client.get("https://www.eci.gov.in/a")


def test_request_budget_enforced() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, content=OLE_XLS)

    budget = RequestBudget(max_requests=2, min_interval_seconds=0)
    with EciStatisticalReportHttpClient(
        transport=httpx.MockTransport(handler), budget=budget
    ) as client:
        client.get("https://www.eci.gov.in/a.xls")
        client.get("https://www.eci.gov.in/b.xls")
        with pytest.raises(CaptureNetworkError, match="request cap"):
            client.get("https://www.eci.gov.in/c.xls")
    assert calls["n"] == 2
    assert MAX_HTTP_ATTEMPTS == 5


def test_403_stops() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="forbidden")

    with EciStatisticalReportHttpClient(
        transport=httpx.MockTransport(handler), budget=RequestBudget(min_interval_seconds=0)
    ) as client:
        with pytest.raises(CaptureNetworkError, match="403"):
            client.get("https://www.eci.gov.in/x.xls")


def test_429_stops() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "60"}, text="slow")

    with EciStatisticalReportHttpClient(
        transport=httpx.MockTransport(handler), budget=RequestBudget(min_interval_seconds=0)
    ) as client:
        with pytest.raises(CaptureNetworkError, match="429"):
            client.get("https://www.eci.gov.in/x.xls")


def test_5xx_retry_bounded() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, text="busy")

    budget = RequestBudget(min_interval_seconds=0)
    with EciStatisticalReportHttpClient(
        transport=httpx.MockTransport(handler), budget=budget
    ) as client:
        with pytest.raises(CaptureNetworkError, match="503"):
            client.get("https://www.eci.gov.in/x.xls")
    assert calls["n"] == 3
    assert budget.requests_made == 3


def test_timeout_retry_bounded() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.ReadTimeout("slow", request=request)

    budget = RequestBudget(min_interval_seconds=0)
    with EciStatisticalReportHttpClient(
        transport=httpx.MockTransport(handler), budget=budget
    ) as client:
        with pytest.raises(CaptureNetworkError, match="timeout"):
            client.get("https://www.eci.gov.in/x.xls")
    assert calls["n"] == 3


def test_response_size_cap_streamed(monkeypatch: pytest.MonkeyPatch) -> None:
    import collectors.eci.statistical_reports.http_client as http_mod

    monkeypatch.setattr(http_mod, "MAX_REPORT_BYTES", 1024)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"x" * 2048,
            headers={"content-type": "application/octet-stream"},
        )

    with EciStatisticalReportHttpClient(
        transport=httpx.MockTransport(handler), budget=RequestBudget(min_interval_seconds=0)
    ) as client:
        with pytest.raises(CaptureNetworkError, match="size cap"):
            client.get("https://www.eci.gov.in/big.xls")


def test_response_size_cap_content_length_header(monkeypatch: pytest.MonkeyPatch) -> None:
    import collectors.eci.statistical_reports.http_client as http_mod

    monkeypatch.setattr(http_mod, "MAX_REPORT_BYTES", 100)

    class _FakeResponse:
        status_code = 200
        headers = {"content-length": "101"}

        def iter_bytes(self, chunk_size: int = 65536):  # noqa: ARG002
            yield b"should-not-be-read"
            return
            yield  # pragma: no cover

        def close(self) -> None:
            return None

    with pytest.raises(CaptureNetworkError, match="Content-Length"):
        http_mod._read_body_limited(_FakeResponse())  # type: ignore[arg-type]


def test_detect_formats() -> None:
    assert detect_container_format(OLE_XLS)[0] == "xls"
    assert detect_container_format(XLSX_ZIP)[0] == "xlsx"
    fmt, reason = detect_container_format(HTML_AS_XLS)
    assert fmt is None
    assert reason and "HTML" in reason


def test_html_masquerading_rejected(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=HTML_AS_XLS, headers={"content-type": "text/html"})

    report = capture_report(
        url="https://www.eci.gov.in/fake.xls",
        report_number="33",
        report_title="Constituency Wise Detailed Result",
        election_year=2024,
        election_type="LOK_SABHA",
        confirm_live=True,
        live_enabled=True,
        raw_root=tmp_path,
        transport=httpx.MockTransport(handler),
        git_commit_sha="test",
    )
    assert report.outcome == "CAPTURE_REJECTED"
    assert report.sha256
    assert report.archive_dir is None


def test_successful_xls_capture_and_idempotent(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=OLE_XLS,
            headers={"content-type": "application/vnd.ms-excel"},
        )

    transport = httpx.MockTransport(handler)
    r1 = capture_report(
        url="https://www.eci.gov.in/report33.xls",
        report_number="33",
        report_title="Constituency Wise Detailed Result",
        election_year=2024,
        election_type="LOK_SABHA",
        confirm_live=True,
        live_enabled=True,
        raw_root=tmp_path,
        transport=transport,
        git_commit_sha="test",
    )
    assert r1.outcome == "SUCCESS"
    assert r1.source_status == "INSERTED"
    assert r1.detected_container_format == "xls"
    assert Path(r1.payload_path).is_file()
    assert Path(r1.archive_dir, "capture_report.json").is_file()

    r2 = capture_report(
        url="https://www.eci.gov.in/report33.xls",
        report_number="33",
        report_title="Constituency Wise Detailed Result",
        election_year=2024,
        election_type="LOK_SABHA",
        confirm_live=True,
        live_enabled=True,
        raw_root=tmp_path,
        transport=transport,
        git_commit_sha="test",
    )
    assert r2.outcome == "SUCCESS"
    assert r2.source_status == "UNCHANGED"
    assert r2.sha256 == r1.sha256


def test_changed_bytes_source_changed_preserves_prior(tmp_path: Path) -> None:
    payloads = {
        "a": OLE_XLS + b"A",
        "b": OLE_XLS + b"B",
    }
    state = {"key": "a"}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payloads[state["key"]])

    transport = httpx.MockTransport(handler)
    r1 = capture_report(
        url="https://www.eci.gov.in/report33.xls",
        report_number="33",
        report_title="Constituency Wise Detailed Result",
        election_year=2024,
        election_type="LOK_SABHA",
        confirm_live=True,
        live_enabled=True,
        raw_root=tmp_path,
        transport=transport,
        git_commit_sha="test",
    )
    assert r1.outcome == "SUCCESS"
    first_dir = Path(r1.archive_dir)
    assert first_dir.is_dir()

    state["key"] = "b"
    # tiny delay so retrieved_at ordering is stable if needed
    time.sleep(0.01)
    r2 = capture_report(
        url="https://www.eci.gov.in/report33.xls",
        report_number="33",
        report_title="Constituency Wise Detailed Result",
        election_year=2024,
        election_type="LOK_SABHA",
        confirm_live=True,
        live_enabled=True,
        raw_root=tmp_path,
        transport=transport,
        git_commit_sha="test",
    )
    assert r2.outcome == "SUCCESS"
    assert r2.source_status == "SOURCE_CHANGED"
    assert r2.sha256 != r1.sha256
    assert first_dir.is_dir()
    assert Path(r1.payload_path).is_file()
    assert Path(r2.archive_dir).is_dir()
    assert Path(r2.archive_dir) != first_dir


def test_capture_does_not_touch_canonical_models(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Capture path must not import/persist Person/Candidacy/ElectionResult."""
    import collectors.eci.statistical_reports.capture as capture_mod

    src = Path(capture_mod.__file__).read_text(encoding="utf-8")
    assert "from packages.db" not in src
    assert "import packages.db" not in src
    assert "models.person" not in src.lower()
    assert "models.candidacy" not in src.lower()
    assert "election_result" not in src.lower()
    assert "sessionmaker" not in src
    assert "Session" not in src

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=XLSX_ZIP)

    report = capture_report(
        url="https://www.eci.gov.in/report33.xlsx",
        report_number="33",
        report_title="Constituency Wise Detailed Result",
        election_year=2024,
        election_type="LOK_SABHA",
        confirm_live=True,
        live_enabled=True,
        raw_root=tmp_path,
        transport=httpx.MockTransport(handler),
        git_commit_sha="test",
    )
    assert isinstance(report, CaptureReport)
    assert report.outcome == "SUCCESS"
    assert report.detected_container_format == "xlsx"
