"""Unit tests for ECI Statistical Report 33 workbook extraction and parsing."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/eci/statistical_reports/report33/report33_schema_fixture.xls"
GOLDEN_WB = ROOT / "tests/fixtures/eci/statistical_reports/report33/golden/expected_workbook.json"
GOLDEN_NORM = (
    ROOT / "tests/fixtures/eci/statistical_reports/report33/golden/expected_normalized.json"
)


def test_detect_ole_xls_magic() -> None:
    from collectors.eci.statistical_reports.schemas import WorkbookFormatStatus
    from collectors.eci.statistical_reports.workbook import detect_workbook_format

    data = FIXTURE.read_bytes()
    assert data[:4] == b"\xd0\xcf\x11\xe0"
    fmt, status, err = detect_workbook_format(data)
    assert fmt == "xls"
    assert status == WorkbookFormatStatus.WORKBOOK_SUPPORTED
    assert err is None


def test_detect_zip_xlsx_magic() -> None:
    from collectors.eci.statistical_reports.schemas import WorkbookFormatStatus
    from collectors.eci.statistical_reports.workbook import detect_workbook_format
    from openpyxl import Workbook

    buf = BytesIO()
    wb = Workbook()
    wb.active.title = "Detailed Results"
    wb.save(buf)
    data = buf.getvalue()
    assert data[:2] == b"PK"
    fmt, status, err = detect_workbook_format(data)
    assert fmt == "xlsx"
    assert status == WorkbookFormatStatus.WORKBOOK_SUPPORTED
    assert err is None


def test_html_masquerading_as_xls_rejected() -> None:
    from collectors.eci.statistical_reports.schemas import WorkbookFormatStatus
    from collectors.eci.statistical_reports.workbook import detect_workbook_format, extract_workbook

    html = b"<!DOCTYPE html><html><body><table><tr><td>State Name</td></tr></table></body></html>"
    fmt, status, err = detect_workbook_format(html)
    assert status == WorkbookFormatStatus.FORMAT_MISMATCH
    assert fmt is None
    assert err and "HTML" in err

    extracted = extract_workbook(html)
    assert extracted.format_status == WorkbookFormatStatus.FORMAT_MISMATCH


def test_corrupt_payload() -> None:
    from collectors.eci.statistical_reports.schemas import WorkbookFormatStatus
    from collectors.eci.statistical_reports.workbook import extract_workbook

    # OLE magic but truncated / invalid CFB body
    data = b"\xd0\xcf\x11\xe0" + b"\x00" * 64
    extracted = extract_workbook(data)
    assert extracted.format_status == WorkbookFormatStatus.CORRUPT


def test_size_limit_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    from collectors.eci.statistical_reports import workbook as wb_mod
    from collectors.eci.statistical_reports.schemas import WorkbookFormatStatus

    monkeypatch.setattr(wb_mod, "MAX_BYTES", 100)
    data = FIXTURE.read_bytes()
    assert len(data) > 100
    fmt, status, err = wb_mod.detect_workbook_format(data)
    assert status == WorkbookFormatStatus.UNSUPPORTED
    assert "MAX_BYTES" in (err or "")


def test_row_limit_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    from collectors.eci.statistical_reports import workbook as wb_mod
    from collectors.eci.statistical_reports.schemas import WorkbookFormatStatus
    from collectors.eci.statistical_reports.workbook import extract_workbook

    monkeypatch.setattr(wb_mod, "MAX_ROWS", 3)
    extracted = extract_workbook(FIXTURE.read_bytes())
    assert extracted.format_status == WorkbookFormatStatus.UNSUPPORTED
    assert "MAX_ROWS" in (extracted.error or "")


def test_schema_match_on_fixture() -> None:
    from collectors.eci.statistical_reports.report33_parser import fingerprint_headers
    from collectors.eci.statistical_reports.schemas import SchemaFingerprintStatus
    from collectors.eci.statistical_reports.workbook import extract_workbook_from_path

    wb = extract_workbook_from_path(FIXTURE)
    sheet = wb.sheets[0]
    status, matched, warnings = fingerprint_headers(sheet.headers)
    assert status == SchemaFingerprintStatus.SCHEMA_MATCH
    assert len(matched) == 17
    assert warnings == []


def test_schema_changed_when_header_renamed() -> None:
    from collectors.eci.statistical_reports.report33_parser import fingerprint_headers
    from collectors.eci.statistical_reports.schemas import SchemaFingerprintStatus
    from collectors.eci.statistical_reports.workbook import extract_workbook_from_path

    wb = extract_workbook_from_path(FIXTURE)
    headers = list(wb.sheets[0].headers)
    headers[0] = "State / UT Name"
    status, matched, warnings = fingerprint_headers(headers)
    assert status == SchemaFingerprintStatus.SCHEMA_CHANGED
    assert matched
    assert any("missing" in w or "unexpected" in w for w in warnings)


def test_golden_workbook_parse() -> None:
    from collectors.eci.statistical_reports.workbook import extract_workbook_from_path

    wb = extract_workbook_from_path(FIXTURE)
    expected = json.loads(GOLDEN_WB.read_text(encoding="utf-8"))
    assert wb.format_status.value == expected["format_status"]
    assert wb.detected_format == expected["detected_format"]
    assert wb.sheet_count == expected["sheet_count"]
    assert wb.sheets[0].headers == expected["sheets"][0]["headers"]
    assert len(wb.sheets[0].rows) == expected["sheets"][0]["row_count"]


def test_golden_normalized_parse() -> None:
    from collectors.eci.statistical_reports.report33_parser import parse_report33_workbook
    from collectors.eci.statistical_reports.workbook import extract_workbook_from_path

    wb = extract_workbook_from_path(FIXTURE)
    report = parse_report33_workbook(wb)
    expected = json.loads(GOLDEN_NORM.read_text(encoding="utf-8"))

    assert report.schema_status.value == expected["schema_status"]
    assert report.parser_version == expected["parser_version"]
    assert len(report.rows) == len(expected["rows"])
    assert report.coverage is not None
    assert report.coverage.coverage_status.value == expected["coverage"]["coverage_status"]
    assert "fixture_subset" in report.coverage.notes

    for got, exp in zip(report.rows, expected["rows"], strict=True):
        assert got.source_row_number == exp["source_row_number"]
        assert got.candidate_name.raw == exp["candidate_name_raw"]
        assert got.candidate_name.normalized == exp["candidate_name_normalized"]
        assert got.votes_value == exp["votes_value"]
        assert got.result_normalized == "UNKNOWN"
        assert got.rank is None
        assert got.row_status.value == exp["row_status"]


def test_skips_blank_and_total_rows() -> None:
    from collectors.eci.statistical_reports.report33_parser import parse_report33_workbook
    from collectors.eci.statistical_reports.workbook import extract_workbook_from_path

    report = parse_report33_workbook(extract_workbook_from_path(FIXTURE))
    names = [r.candidate_name.raw for r in report.rows]
    assert "TOTAL" not in names
    assert None not in names
    assert len(report.rows) == 6
