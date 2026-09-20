from __future__ import annotations

from pathlib import Path

from collectors.eci.affidavits.schemas import ExtractedDocument, ExtractionStatus, TextBlock
from pypdf import PdfReader

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".gif", ".webp", ".bmp"}


def extract_document(path: Path) -> ExtractedDocument:
    """
    Extract machine-readable text from a fixture/document.

    PDF OCR is not implemented; image inputs and PDFs without extractable text
    return OCR_REQUIRED. PDF classification is by content extraction, not filename.
    """
    suffix = path.suffix.lower()

    # Image extensions imply OCR (no text layer expected).
    if suffix in _IMAGE_SUFFIXES:
        return ExtractedDocument(
            extraction_status=ExtractionStatus.OCR_REQUIRED,
            extraction_method="none",
            warnings=["Image document; OCR not implemented in V1"],
        )

    if suffix == ".pdf":
        return _extract_pdf(path)

    try:
        raw = path.read_bytes()
        if b"\x00" in raw[:1024]:
            return ExtractedDocument(
                extraction_status=ExtractionStatus.OCR_REQUIRED,
                extraction_method="none",
                warnings=["Binary content without extractable text"],
            )
        text = raw.decode("utf-8")
    except OSError as exc:
        return ExtractedDocument(
            extraction_status=ExtractionStatus.EXTRACTION_FAILED,
            extraction_method="filesystem",
            warnings=[str(exc)],
        )
    except UnicodeDecodeError:
        return ExtractedDocument(
            extraction_status=ExtractionStatus.OCR_REQUIRED,
            extraction_method="none",
            warnings=["Could not decode as text"],
        )

    if not text.strip():
        return ExtractedDocument(
            extraction_status=ExtractionStatus.EXTRACTION_FAILED,
            extraction_method="text",
            warnings=["Empty document"],
        )

    pages = _split_pages(text)
    return ExtractedDocument(
        extraction_status=ExtractionStatus.TEXT_EXTRACTED,
        extraction_method="plaintext",
        pages=pages,
        full_text=text,
    )


def _split_pages(text: str) -> list[TextBlock]:
    parts = text.split("\f")
    blocks: list[TextBlock] = []
    for i, part in enumerate(parts, start=1):
        for li, line in enumerate(part.splitlines(), start=1):
            if line.strip():
                blocks.append(TextBlock(page_number=i, text=line, line_number=li))
    if not blocks and text.strip():
        blocks.append(TextBlock(page_number=1, text=text.strip(), line_number=1))
    return blocks


def _extract_pdf(path: Path) -> ExtractedDocument:
    try:
        reader = PdfReader(str(path))
        pages: list[TextBlock] = []
        chunks: list[str] = []
        for i, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text() or ""
            chunks.append(page_text)
            for li, line in enumerate(page_text.splitlines(), start=1):
                if line.strip():
                    pages.append(TextBlock(page_number=i, text=line, line_number=li))
        full = "\n".join(chunks).strip()
        if not full:
            return ExtractedDocument(
                extraction_status=ExtractionStatus.OCR_REQUIRED,
                extraction_method="pypdf",
                warnings=["PDF produced no extractable text"],
            )
        return ExtractedDocument(
            extraction_status=ExtractionStatus.TEXT_EXTRACTED,
            extraction_method="pypdf",
            pages=pages,
            full_text=full,
        )
    except OSError as exc:
        return ExtractedDocument(
            extraction_status=ExtractionStatus.EXTRACTION_FAILED,
            extraction_method="pypdf",
            warnings=[str(exc)],
        )
    except Exception as exc:  # noqa: BLE001 — corrupt/unsupported PDF payloads
        return ExtractedDocument(
            extraction_status=ExtractionStatus.EXTRACTION_FAILED,
            extraction_method="pypdf",
            warnings=[str(exc)],
        )
