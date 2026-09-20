"""Workbook format detection and safe extraction (xls / xlsx only)."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from collectors.eci.statistical_reports.schemas import (
    ExtractedCell,
    ExtractedRow,
    ExtractedSheet,
    ExtractedWorkbook,
    WorkbookFormatStatus,
)

MAX_ROWS = 200_000
MAX_COLS = 256
MAX_BYTES = 50_000_000
MAX_SHEETS = 50

OLE_MAGIC = b"\xd0\xcf\x11\xe0"
ZIP_MAGIC = b"PK"
HTML_MARKERS = (b"<!doctype html", b"<html", b"<head", b"<body", b"<table")


def detect_workbook_format(data: bytes) -> tuple[str | None, WorkbookFormatStatus, str | None]:
    """Detect workbook container from magic bytes. Never trust filename alone."""
    if not data:
        return None, WorkbookFormatStatus.CORRUPT, "empty payload"
    if len(data) > MAX_BYTES:
        return None, WorkbookFormatStatus.UNSUPPORTED, f"payload exceeds MAX_BYTES ({MAX_BYTES})"

    head = data[:512].lstrip().lower()
    if any(marker in head for marker in HTML_MARKERS):
        return None, WorkbookFormatStatus.FORMAT_MISMATCH, "HTML content masquerading as workbook"

    if data.startswith(OLE_MAGIC):
        return "xls", WorkbookFormatStatus.WORKBOOK_SUPPORTED, None
    if data.startswith(ZIP_MAGIC):
        # XLSX is a ZIP; reject non-xlsx zip containers later on open.
        return "xlsx", WorkbookFormatStatus.WORKBOOK_SUPPORTED, None

    return None, WorkbookFormatStatus.UNSUPPORTED, "unrecognized magic bytes"


def _cell_to_raw(value: object) -> tuple[str | None, str]:
    if value is None:
        return None, "empty"
    if isinstance(value, bool):
        return ("TRUE" if value else "FALSE"), "bool"
    if isinstance(value, int):
        return str(value), "int"
    if isinstance(value, float):
        if value == int(value) and abs(value) < 1e15:
            return str(int(value)), "int"
        # Preserve decimal string without scientific notation noise when possible.
        text = repr(value) if abs(value) < 1e-4 or abs(value) >= 1e12 else f"{value}"
        if "e" in text.lower():
            text = format(value, "f").rstrip("0").rstrip(".")
        return text, "float"
    text = str(value).strip()
    if text == "":
        return None, "empty"
    return text, "str"


def _extract_xls(data: bytes) -> ExtractedWorkbook:
    import xlrd

    try:
        book = xlrd.open_workbook(file_contents=data, formatting_info=False)
    except Exception as exc:  # noqa: BLE001 — surface as CORRUPT
        return ExtractedWorkbook(
            format_status=WorkbookFormatStatus.CORRUPT,
            detected_format="xls",
            error=f"xlrd open failed: {exc}",
        )

    if book.nsheets > MAX_SHEETS:
        return ExtractedWorkbook(
            format_status=WorkbookFormatStatus.UNSUPPORTED,
            detected_format="xls",
            sheet_count=book.nsheets,
            error=f"sheet count {book.nsheets} exceeds MAX_SHEETS ({MAX_SHEETS})",
        )

    sheets: list[ExtractedSheet] = []
    warnings: list[str] = []
    for sheet_idx in range(book.nsheets):
        sh = book.sheet_by_index(sheet_idx)
        if sh.ncols > MAX_COLS:
            return ExtractedWorkbook(
                format_status=WorkbookFormatStatus.UNSUPPORTED,
                detected_format="xls",
                sheet_count=book.nsheets,
                error=f"sheet {sh.name!r} has {sh.ncols} cols > MAX_COLS ({MAX_COLS})",
            )
        if sh.nrows > MAX_ROWS:
            return ExtractedWorkbook(
                format_status=WorkbookFormatStatus.UNSUPPORTED,
                detected_format="xls",
                sheet_count=book.nsheets,
                error=f"sheet {sh.name!r} has {sh.nrows} rows > MAX_ROWS ({MAX_ROWS})",
            )

        headers: list[str] = []
        if sh.nrows > 0:
            for c in range(sh.ncols):
                cell = sh.cell(0, c)
                # ctype 5 = error; never evaluate formulas — use cached value only.
                raw, _ = _cell_to_raw(cell.value if cell.ctype != xlrd.XL_CELL_ERROR else None)
                headers.append(raw or f"COL_{c}")

        rows: list[ExtractedRow] = []
        for r in range(1, sh.nrows):
            cells: list[ExtractedCell] = []
            raw_by_header: dict[str, str | None] = {}
            for c in range(sh.ncols):
                cell = sh.cell(r, c)
                if cell.ctype == xlrd.XL_CELL_ERROR:
                    raw, vtype = None, "error"
                elif cell.ctype == xlrd.XL_CELL_EMPTY:
                    raw, vtype = None, "empty"
                else:
                    # XL_CELL_FORMULA still exposes cached value via .value; do not recompute.
                    raw, vtype = _cell_to_raw(cell.value)
                header = headers[c] if c < len(headers) else f"COL_{c}"
                cells.append(
                    ExtractedCell(column_index=c, header=header, raw_value=raw, value_type=vtype)
                )
                raw_by_header[header] = raw
            rows.append(
                ExtractedRow(
                    sheet_name=sh.name,
                    source_row_number=r,
                    cells=cells,
                    raw_by_header=raw_by_header,
                )
            )
        sheets.append(ExtractedSheet(name=sh.name, headers=headers, rows=rows))

    return ExtractedWorkbook(
        format_status=WorkbookFormatStatus.WORKBOOK_SUPPORTED,
        detected_format="xls",
        sheet_count=len(sheets),
        sheets=sheets,
        warnings=warnings,
    )


def _extract_xlsx(data: bytes) -> ExtractedWorkbook:
    from openpyxl import load_workbook

    try:
        # data_only=True reads cached values only; never evaluates formulas.
        book = load_workbook(filename=BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001
        return ExtractedWorkbook(
            format_status=WorkbookFormatStatus.CORRUPT,
            detected_format="xlsx",
            error=f"openpyxl open failed: {exc}",
        )

    try:
        sheet_names = list(book.sheetnames)
        if len(sheet_names) > MAX_SHEETS:
            return ExtractedWorkbook(
                format_status=WorkbookFormatStatus.UNSUPPORTED,
                detected_format="xlsx",
                sheet_count=len(sheet_names),
                error=f"sheet count {len(sheet_names)} exceeds MAX_SHEETS ({MAX_SHEETS})",
            )

        sheets: list[ExtractedSheet] = []
        for name in sheet_names:
            ws = book[name]
            row_iter = ws.iter_rows(values_only=True)
            try:
                header_tuple = next(row_iter)
            except StopIteration:
                sheets.append(ExtractedSheet(name=name, headers=[], rows=[]))
                continue

            if len(header_tuple) > MAX_COLS:
                return ExtractedWorkbook(
                    format_status=WorkbookFormatStatus.UNSUPPORTED,
                    detected_format="xlsx",
                    sheet_count=len(sheet_names),
                    error=f"sheet {name!r} exceeds MAX_COLS ({MAX_COLS})",
                )

            headers: list[str] = []
            for c, val in enumerate(header_tuple):
                raw, _ = _cell_to_raw(val)
                headers.append(raw or f"COL_{c}")

            rows: list[ExtractedRow] = []
            for r_idx, values in enumerate(row_iter, start=1):
                if r_idx >= MAX_ROWS:
                    return ExtractedWorkbook(
                        format_status=WorkbookFormatStatus.UNSUPPORTED,
                        detected_format="xlsx",
                        sheet_count=len(sheet_names),
                        error=f"sheet {name!r} exceeds MAX_ROWS ({MAX_ROWS})",
                    )
                if len(values) > MAX_COLS:
                    return ExtractedWorkbook(
                        format_status=WorkbookFormatStatus.UNSUPPORTED,
                        detected_format="xlsx",
                        sheet_count=len(sheet_names),
                        error=f"sheet {name!r} exceeds MAX_COLS ({MAX_COLS})",
                    )
                cells: list[ExtractedCell] = []
                raw_by_header: dict[str, str | None] = {}
                for c, val in enumerate(values):
                    raw, vtype = _cell_to_raw(val)
                    header = headers[c] if c < len(headers) else f"COL_{c}"
                    cells.append(
                        ExtractedCell(
                            column_index=c, header=header, raw_value=raw, value_type=vtype
                        )
                    )
                    raw_by_header[header] = raw
                # Pad missing trailing headers
                for c in range(len(values), len(headers)):
                    header = headers[c]
                    cells.append(
                        ExtractedCell(
                            column_index=c, header=header, raw_value=None, value_type="empty"
                        )
                    )
                    raw_by_header[header] = None
                rows.append(
                    ExtractedRow(
                        sheet_name=name,
                        source_row_number=r_idx,
                        cells=cells,
                        raw_by_header=raw_by_header,
                    )
                )
            sheets.append(ExtractedSheet(name=name, headers=headers, rows=rows))

        return ExtractedWorkbook(
            format_status=WorkbookFormatStatus.WORKBOOK_SUPPORTED,
            detected_format="xlsx",
            sheet_count=len(sheets),
            sheets=sheets,
        )
    finally:
        book.close()


def extract_workbook(data: bytes) -> ExtractedWorkbook:
    fmt, status, err = detect_workbook_format(data)
    if status != WorkbookFormatStatus.WORKBOOK_SUPPORTED:
        return ExtractedWorkbook(format_status=status, detected_format=fmt, error=err)
    if fmt == "xls":
        return _extract_xls(data)
    if fmt == "xlsx":
        return _extract_xlsx(data)
    return ExtractedWorkbook(
        format_status=WorkbookFormatStatus.UNSUPPORTED,
        detected_format=fmt,
        error="unsupported format",
    )


def extract_workbook_from_path(path: Path) -> ExtractedWorkbook:
    data = path.read_bytes()
    return extract_workbook(data)
