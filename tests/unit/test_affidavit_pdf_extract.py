"""PDF extraction and filename-vs-content OCR detection."""

from __future__ import annotations

from pathlib import Path

from collectors.eci.affidavits.extract import extract_document
from collectors.eci.affidavits.parser import parse_extracted_document
from collectors.eci.affidavits.schemas import ExtractionStatus

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures/eci/affidavits"


def test_pdf_fixture_extracts_via_pypdf() -> None:
    doc = extract_document(FIXTURES / "asha_verma_form26.pdf")
    assert doc.extraction_status == ExtractionStatus.TEXT_EXTRACTED
    assert doc.extraction_method == "pypdf"
    assert doc.pages
    assert all(p.page_number >= 1 for p in doc.pages)
    assert "Asha Verma" in doc.full_text
    assert "Bachelor of Engineering" in doc.full_text
    parsed = parse_extracted_document(doc)
    assert parsed.candidate_name_raw == "Asha Verma"
    assert parsed.assets


def test_pdf_filename_scanned_still_extracts_when_text_present() -> None:
    doc = extract_document(FIXTURES / "scanned_form.pdf")
    assert doc.extraction_status == ExtractionStatus.TEXT_EXTRACTED
    assert doc.extraction_method == "pypdf"
    assert "Asha Verma" in doc.full_text


def test_image_extension_implies_ocr() -> None:
    # Synthetic empty png path is not needed — suffix gate is unit-tested via temp file
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as fh:
        path = Path(fh.name)
        fh.write(b"\x89PNG\r\n\x1a\n")
    try:
        doc = extract_document(path)
        assert doc.extraction_status == ExtractionStatus.OCR_REQUIRED
    finally:
        path.unlink(missing_ok=True)
