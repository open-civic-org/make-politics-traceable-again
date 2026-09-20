"""Conservative workbook container detection (no formula/macro execution)."""

from __future__ import annotations

import io
import zipfile

OLE_MAGIC = b"\xd0\xcf\x11\xe0"
ZIP_MAGIC = b"PK"
HTML_MARKERS = (b"<!doctype html", b"<html", b"<head", b"<body", b"<table")

# Required OOXML workbook members (central-directory names).
OOXML_REQUIRED_MEMBERS = frozenset(
    {
        "[Content_Types].xml",
        "xl/workbook.xml",
    }
)


def _looks_like_html(data: bytes) -> bool:
    head = data[:512].lstrip().lower()
    return any(marker in head for marker in HTML_MARKERS)


def _zip_member_names(data: bytes) -> set[str] | None:
    """Return ZIP central-directory names, or None if not a readable ZIP."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            # Force central-directory parse; BadZipFile on corruption.
            names = set(zf.namelist())
            _ = zf.infolist()
            return names
    except (zipfile.BadZipFile, OSError, ValueError):
        return None


def detect_container_format(data: bytes) -> tuple[str | None, str | None]:
    """Return (format, rejection_reason).

    Formats:
      - ``xlsx`` — OOXML ZIP containing required workbook members
      - ``OLE_CFB`` — OLE compound-file magic (not confirmed Excel)
      - ``None`` — rejected / unsupported
    """
    if not data:
        return None, "empty payload"
    if _looks_like_html(data):
        return None, "HTML content masquerading as workbook"

    if data.startswith(OLE_MAGIC):
        # CFB/OLE container only — do not assert legacy Excel workbook.
        return "OLE_CFB", None

    if data.startswith(ZIP_MAGIC):
        names = _zip_member_names(data)
        if names is None:
            return None, "malformed or unreadable ZIP"
        missing = OOXML_REQUIRED_MEMBERS - names
        if missing:
            return None, (f"ZIP is not an OOXML workbook (missing: {', '.join(sorted(missing))})")
        return "xlsx", None

    return None, "unsupported binary format"
