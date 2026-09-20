"""Offline tests for guarded ECI statistical-report capture."""

from __future__ import annotations

import io
import json
import re
import time
import zipfile
from pathlib import Path

import httpx
import pytest
import yaml
from collectors.eci.statistical_reports.capture import (
    ARTIFACT_NAME_RE,
    CaptureReport,
    capture_report,
    detect_container_format,
    validate_report_number,
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

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = ROOT / ".github/workflows/eci-statistical-report-capture.yml"

OLE_CFB = b"\xd0\xcf\x11\xe0" + b"\x00" * 64
HTML_AS_XLS = b"<!DOCTYPE html><html><body>not a workbook</body></html>"


def _minimal_ooxml_workbook() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"></Types>',
        )
        zf.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"></workbook>',
        )
    return buf.getvalue()


def _generic_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", "not a workbook")
    return buf.getvalue()


XLSX_OOXML = _minimal_ooxml_workbook()
GENERIC_ZIP = _generic_zip()
CORRUPT_ZIP = b"PK\x03\x04" + b"\x00" * 32  # ZIP local-header magic, truncated


def test_live_disabled_by_default() -> None:
    from packages.shared.config import Settings

    assert Settings().eci_stat_report_live_enabled is False
    with pytest.raises(CaptureAccessError):
        assert_live_enabled(False)


def test_confirm_live_required(tmp_path: Path) -> None:
    report = capture_report(
        url="https://www.eci.gov.in/file.xls",
        report_number=33,
        report_title="Constituency Wise Detailed Result",
        election_year=2024,
        election_type="LOK_SABHA",
        confirm_live=False,
        live_enabled=True,
        raw_root=tmp_path,
    )
    assert report.outcome == "FAILED"
    assert "--confirm-live" in (report.error or "")


@pytest.mark.parametrize(
    "bad",
    [
        "../../outside",
        "../33",
        "33/evil",
        "33\\evil",
        "33\nartifact_name=pwned",
        "33;touch-x",
        "abc",
        "0",
        "-1",
        "1.5",
        "10000",
        "",
        " 33",
        "33 ",
    ],
)
def test_report_number_rejects_path_injection(bad: str, tmp_path: Path) -> None:
    with pytest.raises(CaptureAccessError):
        validate_report_number(bad)

    report = capture_report(
        url="https://www.eci.gov.in/file.xls",
        report_number=bad,
        report_title="Constituency Wise Detailed Result",
        election_year=2024,
        election_type="LOK_SABHA",
        confirm_live=True,
        live_enabled=True,
        raw_root=tmp_path,
    )
    assert report.outcome == "FAILED"
    assert report.archive_dir is None
    assert not any(tmp_path.rglob("*"))


def test_report_number_accepts_positive_integers() -> None:
    assert validate_report_number(1) == "1"
    assert validate_report_number(33) == "33"
    assert validate_report_number("42") == "42"
    assert validate_report_number(9999) == "9999"


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
            return httpx.Response(200, content=OLE_CFB)
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
            content=OLE_CFB,
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
        return httpx.Response(200, content=OLE_CFB)

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


def test_detect_ooxml_workbook() -> None:
    assert detect_container_format(XLSX_OOXML)[0] == "xlsx"


def test_detect_generic_zip_rejected() -> None:
    fmt, reason = detect_container_format(GENERIC_ZIP)
    assert fmt is None
    assert reason and "OOXML" in reason


def test_detect_corrupt_zip_rejected() -> None:
    fmt, reason = detect_container_format(CORRUPT_ZIP)
    assert fmt is None
    assert reason and "ZIP" in reason


def test_detect_ole_cfb_not_xls() -> None:
    fmt, reason = detect_container_format(OLE_CFB)
    assert fmt == "OLE_CFB"
    assert reason is None
    assert fmt != "xls"


def test_detect_html_rejected() -> None:
    fmt, reason = detect_container_format(HTML_AS_XLS)
    assert fmt is None
    assert reason and "HTML" in reason


def test_html_masquerading_rejected(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=HTML_AS_XLS, headers={"content-type": "text/html"})

    report = capture_report(
        url="https://www.eci.gov.in/fake.xls",
        report_number=33,
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


def test_fresh_archive_root_is_first_observation(tmp_path: Path) -> None:
    """Ephemeral runners have empty raw_root → FIRST_OBSERVATION, not INSERTED."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=OLE_CFB)

    report = capture_report(
        url="https://www.eci.gov.in/report33.xls",
        report_number=33,
        report_title="Constituency Wise Detailed Result",
        election_year=2024,
        election_type="LOK_SABHA",
        confirm_live=True,
        live_enabled=True,
        raw_root=tmp_path,
        transport=httpx.MockTransport(handler),
        git_commit_sha="test",
    )
    assert report.outcome == "SUCCESS"
    assert report.source_status == "FIRST_OBSERVATION"
    assert report.detected_container_format == "OLE_CFB"
    assert report.report_number == "33"
    assert report.artifact_name is not None
    assert ARTIFACT_NAME_RE.fullmatch(report.artifact_name)
    assert "/" not in report.artifact_name
    assert "\\" not in report.artifact_name
    assert "\n" not in report.artifact_name
    assert "=" not in report.artifact_name

    archive = Path(report.archive_dir).resolve()
    expected_root = (tmp_path / "eci" / "statistical_reports").resolve()
    assert archive.is_relative_to(expected_root)
    assert "report_33" in archive.parts


def test_persistent_prior_unchanged_and_source_changed(tmp_path: Path) -> None:
    payloads = {
        "a": OLE_CFB + b"A",
        "b": OLE_CFB + b"B",
    }
    state = {"key": "a"}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payloads[state["key"]])

    transport = httpx.MockTransport(handler)
    r1 = capture_report(
        url="https://www.eci.gov.in/report33.xls",
        report_number=33,
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
    assert r1.source_status == "FIRST_OBSERVATION"
    first_dir = Path(r1.archive_dir)
    assert first_dir.is_dir()

    r2 = capture_report(
        url="https://www.eci.gov.in/report33.xls",
        report_number=33,
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

    state["key"] = "b"
    time.sleep(0.01)
    r3 = capture_report(
        url="https://www.eci.gov.in/report33.xls",
        report_number=33,
        report_title="Constituency Wise Detailed Result",
        election_year=2024,
        election_type="LOK_SABHA",
        confirm_live=True,
        live_enabled=True,
        raw_root=tmp_path,
        transport=transport,
        git_commit_sha="test",
    )
    assert r3.outcome == "SUCCESS"
    assert r3.source_status == "SOURCE_CHANGED"
    assert r3.sha256 != r1.sha256
    assert first_dir.is_dir()
    assert Path(r1.payload_path).is_file()
    assert Path(r3.archive_dir) != first_dir


def test_generic_zip_capture_rejected(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=GENERIC_ZIP)

    report = capture_report(
        url="https://www.eci.gov.in/not-workbook.zip",
        report_number=33,
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
    assert report.archive_dir is None


def test_ooxml_capture_success(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=XLSX_OOXML)

    report = capture_report(
        url="https://www.eci.gov.in/report33.xlsx",
        report_number=33,
        report_title="Constituency Wise Detailed Result",
        election_year=2024,
        election_type="LOK_SABHA",
        confirm_live=True,
        live_enabled=True,
        raw_root=tmp_path,
        transport=httpx.MockTransport(handler),
        git_commit_sha="test",
    )
    assert report.outcome == "SUCCESS"
    assert report.detected_container_format == "xlsx"
    assert report.source_status == "FIRST_OBSERVATION"


def test_capture_does_not_touch_canonical_models(tmp_path: Path) -> None:
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
        return httpx.Response(200, content=XLSX_OOXML)

    report = capture_report(
        url="https://www.eci.gov.in/report33.xlsx",
        report_number=33,
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


def test_workflow_no_shell_interpolation_of_inputs() -> None:
    """workflow_dispatch inputs must not be interpolated into shell source."""
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "capture_only" not in text

    # No ${{ inputs.* }} inside executable shell run blocks.
    # Inputs may only appear in the env: mapping for the capture step.
    doc = yaml.safe_load(text)
    # PyYAML may parse the workflow key `on:` as boolean True.
    on_block = doc.get("on") or doc.get(True)
    assert set(on_block["workflow_dispatch"]["inputs"].keys()) == {
        "report_url",
        "report_number",
        "report_title",
        "election_year",
        "election_type",
    }

    capture_step = next(
        step for step in doc["jobs"]["capture"]["steps"] if step.get("id") == "capture"
    )
    env = capture_step["env"]
    assert env["ECI_REPORT_URL"] == "${{ inputs.report_url }}"
    assert env["ECI_REPORT_NUMBER"] == "${{ inputs.report_number }}"
    assert env["ECI_REPORT_TITLE"] == "${{ inputs.report_title }}"
    assert env["ECI_ELECTION_YEAR"] == "${{ inputs.election_year }}"
    assert env["ECI_ELECTION_TYPE"] == "${{ inputs.election_type }}"

    run_script = capture_step["run"]
    assert "${{ inputs." not in run_script
    assert "$ECI_REPORT_URL" in run_script
    assert "$ECI_REPORT_TITLE" in run_script

    # Entire workflow file: inputs.* only appear under env / inputs schema, never as shell.
    for match in re.finditer(r"\$\{\{\s*inputs\.[^}]+\}\}", text):
        # Allowed only on the same line as an env assignment (KEY: ${{ inputs... }})
        line_start = text.rfind("\n", 0, match.start()) + 1
        line = text[line_start : text.find("\n", match.start())]
        assert re.match(r"\s+[A-Z0-9_]+:\s*\$\{\{\s*inputs\.", line), (
            f"inputs expression must be env-mapped only, found: {line!r}"
        )


def test_cli_treats_malicious_title_as_data(tmp_path: Path) -> None:
    """Metacharacters in title must remain data (never executed as shell)."""
    malicious_title = 'Report"; rm -rf /; echo "$(whoami)`id`\n\'DROP'
    safe_url = "https://www.eci.gov.in/report33.xls"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=OLE_CFB)

    report = capture_report(
        url=safe_url,
        report_number=33,
        report_title=malicious_title,
        election_year=2024,
        election_type="LOK_SABHA",
        confirm_live=True,
        live_enabled=True,
        raw_root=tmp_path,
        transport=httpx.MockTransport(handler),
        git_commit_sha="test",
    )
    assert report.outcome == "SUCCESS"
    assert report.report_title == malicious_title
    meta = json.loads((Path(report.archive_dir) / "metadata.json").read_text(encoding="utf-8"))
    assert meta["report_title"] == malicious_title


def test_workflow_env_preserves_shell_metacharacters_as_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulate workflow env→argv path: quoted env vars stay data for argparse."""
    import os
    import subprocess
    import sys

    malicious = 'evil"; $(reboot); `id`; \n\'"'
    monkeypatch.setenv("ECI_REPORT_URL", "https://www.eci.gov.in/r.xls")
    monkeypatch.setenv("ECI_REPORT_NUMBER", "33")
    monkeypatch.setenv("ECI_REPORT_TITLE", malicious)
    monkeypatch.setenv("ECI_ELECTION_YEAR", "2024")
    monkeypatch.setenv("ECI_ELECTION_TYPE", "LOK_SABHA")

    script = """
import argparse, os
p = argparse.ArgumentParser()
p.add_argument("--url")
p.add_argument("--report-number")
p.add_argument("--report-title")
p.add_argument("--election-year", type=int)
p.add_argument("--election-type")
args = p.parse_args([
    "--url", os.environ["ECI_REPORT_URL"],
    "--report-number", os.environ["ECI_REPORT_NUMBER"],
    "--report-title", os.environ["ECI_REPORT_TITLE"],
    "--election-year", os.environ["ECI_ELECTION_YEAR"],
    "--election-type", os.environ["ECI_ELECTION_TYPE"],
])
assert args.report_title == os.environ["ECI_REPORT_TITLE"]
print("ok", len(args.report_title))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    assert "ok" in result.stdout
