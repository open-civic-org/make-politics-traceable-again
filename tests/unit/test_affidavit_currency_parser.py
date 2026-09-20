"""Unit tests for Indian currency parsing and affidavit normalize/extract."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from collectors.eci.affidavits.currency import AmountParseStatus, parse_indian_amount
from collectors.eci.affidavits.extract import extract_document
from collectors.eci.affidavits.normalize import normalize_affidavit
from collectors.eci.affidavits.parser import parse_extracted_document
from collectors.eci.affidavits.schemas import EducationLevel, ExtractionStatus, ParseOutcome

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures/eci/affidavits"


@pytest.mark.parametrize(
    ("raw", "value", "status"),
    [
        ("₹1,23,45,678", Decimal("12345678"), AmountParseStatus.EXACT),
        ("Rs 1,23,45,678", Decimal("12345678"), AmountParseStatus.EXACT),
        ("Rs. 1,23,45,678", Decimal("12345678"), AmountParseStatus.EXACT),
        ("1,23,45,678", Decimal("12345678"), AmountParseStatus.EXACT),
        ("0", Decimal("0"), AmountParseStatus.EXACT),
        ("Nil", Decimal("0"), AmountParseStatus.ZERO),
        ("NIL", Decimal("0"), AmountParseStatus.ZERO),
        ("Not Applicable", None, AmountParseStatus.NOT_APPLICABLE),
        ("-", None, AmountParseStatus.NOT_APPLICABLE),
        ("", None, AmountParseStatus.MISSING),
        (None, None, AmountParseStatus.MISSING),
        ("approx lots", None, AmountParseStatus.PARSE_FAILED),
    ],
)
def test_parse_indian_amount(raw, value, status) -> None:
    parsed = parse_indian_amount(raw)
    assert parsed.status == status
    assert parsed.amount_value == value
    if value is not None:
        assert isinstance(parsed.amount_value, Decimal)


def test_nil_never_confused_with_missing() -> None:
    assert parse_indian_amount("Nil").amount_value == Decimal("0")
    assert parse_indian_amount(None).amount_value is None
    assert parse_indian_amount("garbage!!!").status == AmountParseStatus.PARSE_FAILED
    assert parse_indian_amount("garbage!!!").amount_value is None


def test_extract_and_parse_fixture() -> None:
    doc = extract_document(FIXTURES / "asha_verma_form26.txt")
    assert doc.extraction_status == ExtractionStatus.TEXT_EXTRACTED
    parsed = parse_extracted_document(doc)
    assert parsed.candidate_name_raw == "Asha Verma"
    assert parsed.section_status["education"] == "PARSED"
    assert parsed.section_status["assets"] == "PARSED"
    assert parsed.section_status["criminal_cases"] == "PARSED"
    assert parsed.cases == []
    normalized = normalize_affidavit(parsed)
    assert normalized.education[0].normalized_level == EducationLevel.GRADUATE
    assert normalized.assets[-1].amount_value == Decimal("12345678")
    assert normalized.liabilities[0].amount_value == Decimal("500000")


def test_partial_criminal_needs_review() -> None:
    doc = extract_document(FIXTURES / "bharat_mehta_partial.txt")
    parsed = parse_extracted_document(doc)
    assert parsed.section_status["education"] == "PARSED"
    assert parsed.section_status["criminal_cases"] == "NEEDS_REVIEW"
    normalized = normalize_affidavit(parsed)
    assert normalized.parse_outcome == ParseOutcome.PARTIAL
    assert len(normalized.cases) == 1


def test_scanned_requires_ocr() -> None:
    doc = extract_document(FIXTURES / "scanned_ocr_required.bin")
    assert doc.extraction_status == ExtractionStatus.OCR_REQUIRED
    assert not doc.full_text.strip()


def test_parse_failed_amount_not_zeroed() -> None:
    doc = extract_document(FIXTURES / "asha_verma_parse_failed_amount.txt")
    parsed = parse_extracted_document(doc)
    normalized = normalize_affidavit(parsed)
    assert normalized.parse_outcome == ParseOutcome.PARTIAL
    asset = normalized.assets[0]
    assert asset.field_status.value == "PARSE_FAILED"
    assert asset.amount_value is None
    assert asset.amount_raw == "approx lots of money"
