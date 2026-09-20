"""Report 33 schema fingerprint and row parser."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from collectors.eci.statistical_reports.normalize import normalize_header_key, normalize_name
from collectors.eci.statistical_reports.schemas import (
    PARSER_VERSION,
    REPORT33_NUMBER,
    REPORT33_SHEET_NAME,
    REPORT33_TITLE,
    ExtractedSheet,
    ExtractedWorkbook,
    FieldStatus,
    FieldValue,
    ParsedResultRow,
    ParsedStatisticalReport,
    RowStatus,
    SchemaFingerprintStatus,
    WorkbookFormatStatus,
)
from collectors.eci.statistical_reports.validation import (
    build_coverage_report,
    validate_parsed_rows,
)

# Canonical Report 33 headers → semantic field keys (case-insensitive after normalize).
REPORT33_HEADER_MAP: dict[str, str] = {
    normalize_header_key("State Name"): "state",
    normalize_header_key("PC Name"): "constituency_name",
    normalize_header_key("Candidate Name"): "candidate_name",
    normalize_header_key("Gender"): "gender",
    normalize_header_key("Age"): "age",
    normalize_header_key("Category"): "category",
    normalize_header_key("Party Name"): "party_name",
    normalize_header_key("Party Symbol"): "symbol",
    normalize_header_key("Total Votes Polled In The Constituency"): "total_votes_polled",
    normalize_header_key("Valid Votes"): "valid_votes",
    normalize_header_key("Votes Secured - General"): "votes_general",
    normalize_header_key("Votes Secured - Postal"): "votes_postal",
    normalize_header_key("Votes Secured - Total"): "votes",
    normalize_header_key(
        "% of Votes Secured - Over Total Electors In Constituency"
    ): "vote_share_over_electors",
    normalize_header_key(
        "% of Votes Secured - Over Total Votes Polled In Constituency"
    ): "vote_share_over_polled",
    normalize_header_key("Over Total Valid Votes Polled In Constituency"): "vote_share",
    normalize_header_key("Total Electors"): "total_electors",
}

REQUIRED_SEMANTIC_KEYS = frozenset(REPORT33_HEADER_MAP.values())

_TOTAL_RE = re.compile(r"^total\b", re.IGNORECASE)


def fingerprint_headers(
    headers: list[str],
) -> tuple[SchemaFingerprintStatus, dict[str, str], list[str]]:
    """
    Match observed headers to the Report 33 map.

    Returns (status, observed_normalized→semantic_key, warnings).
    """
    observed: dict[str, str] = {}
    warnings: list[str] = []
    for h in headers:
        key = normalize_header_key(h)
        if not key:
            continue
        if key in observed:
            warnings.append(f"duplicate header after normalize: {h!r}")
            continue
        observed[key] = h

    matched: dict[str, str] = {}
    for norm_key in observed:
        semantic = REPORT33_HEADER_MAP.get(norm_key)
        if semantic is not None:
            matched[norm_key] = semantic

    required_norms = set(REPORT33_HEADER_MAP.keys())
    observed_norms = set(observed.keys())
    missing = required_norms - observed_norms
    extra = observed_norms - required_norms

    if not missing and not extra and len(matched) == len(REPORT33_HEADER_MAP):
        return SchemaFingerprintStatus.SCHEMA_MATCH, matched, warnings

    if missing and not matched:
        return SchemaFingerprintStatus.SCHEMA_UNSUPPORTED, matched, warnings

    # Partial overlap or renamed columns → SCHEMA_CHANGED (still may parse overlapping fields).
    if matched:
        if missing:
            warnings.append(f"missing headers: {sorted(missing)}")
        if extra:
            warnings.append(f"unexpected headers: {sorted(extra)}")
        return SchemaFingerprintStatus.SCHEMA_CHANGED, matched, warnings

    return SchemaFingerprintStatus.SCHEMA_UNSUPPORTED, matched, warnings


def _text_field(raw: str | None, *, normalize: bool = False) -> FieldValue:
    if raw is None or str(raw).strip() == "":
        return FieldValue(raw=None, normalized=None, status=FieldStatus.MISSING)
    text = str(raw).strip()
    if normalize:
        return FieldValue(
            raw=text,
            normalized=normalize_name(text),
            status=FieldStatus.NORMALIZED,
        )
    return FieldValue(raw=text, normalized=text, status=FieldStatus.EXACT)


def _parse_int(raw: str | None) -> tuple[FieldValue, int | None]:
    if raw is None or str(raw).strip() == "":
        return FieldValue(raw=None, normalized=None, status=FieldStatus.MISSING), None
    text = str(raw).strip().replace(",", "")
    try:
        # Allow "45.0" from spreadsheet floats.
        value = int(Decimal(text))
    except (InvalidOperation, ValueError):
        return FieldValue(raw=text, normalized=None, status=FieldStatus.INVALID), None
    return FieldValue(raw=text, normalized=str(value), status=FieldStatus.EXACT), value


def _parse_decimal(raw: str | None) -> tuple[FieldValue, Decimal | None]:
    if raw is None or str(raw).strip() == "":
        return FieldValue(raw=None, normalized=None, status=FieldStatus.MISSING), None
    text = str(raw).strip().replace(",", "").rstrip("%")
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError):
        return FieldValue(raw=text, normalized=None, status=FieldStatus.INVALID), None
    # Quantize lightly for Numeric(8,4) storage without inventing precision.
    q = value.quantize(Decimal("0.0001")) if value.as_tuple().exponent < -4 else value
    return FieldValue(raw=text, normalized=str(q), status=FieldStatus.EXACT), q


def _is_blank_row(raw_by_header: dict[str, str | None]) -> bool:
    return all(v is None or str(v).strip() == "" for v in raw_by_header.values())


def _is_total_footer(raw_by_header: dict[str, str | None], semantic_lookup: dict[str, str]) -> bool:
    # TOTAL often appears in the first column (State Name) or Candidate Name.
    for semantic in ("state", "candidate_name", "constituency_name"):
        # invert: find observed header for semantic
        for norm, sem in semantic_lookup.items():
            if sem != semantic:
                continue
            # find raw value for original header matching norm
            for header, val in raw_by_header.items():
                if normalize_header_key(header) != norm or not val:
                    continue
                if _TOTAL_RE.match(str(val).strip()):
                    return True
    # Fallback: any cell equals TOTAL
    for val in raw_by_header.values():
        if val and str(val).strip().upper() == "TOTAL":
            return True
    return False


def _lookup(
    raw_by_header: dict[str, str | None],
    semantic_lookup: dict[str, str],
    semantic: str,
) -> str | None:
    for norm, sem in semantic_lookup.items():
        if sem != semantic:
            continue
        for header, val in raw_by_header.items():
            if normalize_header_key(header) == norm:
                return val
    return None


def _parse_data_row(
    *,
    sheet_name: str,
    source_row_number: int,
    raw_by_header: dict[str, str | None],
    semantic_lookup: dict[str, str],
) -> ParsedResultRow:
    raw_row: dict[str, Any] = {k: v for k, v in raw_by_header.items()}

    state = _text_field(_lookup(raw_by_header, semantic_lookup, "state"), normalize=True)
    constituency_name = _text_field(
        _lookup(raw_by_header, semantic_lookup, "constituency_name"), normalize=True
    )
    candidate_name = _text_field(
        _lookup(raw_by_header, semantic_lookup, "candidate_name"), normalize=True
    )
    party_name = _text_field(_lookup(raw_by_header, semantic_lookup, "party_name"), normalize=True)
    gender = _text_field(_lookup(raw_by_header, semantic_lookup, "gender"))
    age = _text_field(_lookup(raw_by_header, semantic_lookup, "age"))
    category = _text_field(_lookup(raw_by_header, semantic_lookup, "category"))
    symbol = _text_field(_lookup(raw_by_header, semantic_lookup, "symbol"))

    votes_fv, votes_value = _parse_int(_lookup(raw_by_header, semantic_lookup, "votes"))
    vote_share_fv, vote_share_value = _parse_decimal(
        _lookup(raw_by_header, semantic_lookup, "vote_share")
    )
    votes_general_fv, votes_general_value = _parse_int(
        _lookup(raw_by_header, semantic_lookup, "votes_general")
    )
    votes_postal_fv, votes_postal_value = _parse_int(
        _lookup(raw_by_header, semantic_lookup, "votes_postal")
    )
    total_electors_fv, total_electors_value = _parse_int(
        _lookup(raw_by_header, semantic_lookup, "total_electors")
    )
    valid_votes_fv, valid_votes_value = _parse_int(
        _lookup(raw_by_header, semantic_lookup, "valid_votes")
    )
    total_votes_polled_fv, total_votes_polled_value = _parse_int(
        _lookup(raw_by_header, semantic_lookup, "total_votes_polled")
    )

    return ParsedResultRow(
        sheet_name=sheet_name,
        source_row_number=source_row_number,
        state=state,
        constituency_number=FieldValue(status=FieldStatus.MISSING),
        constituency_name=constituency_name,
        candidate_name=candidate_name,
        party_name=party_name,
        gender=gender,
        age=age,
        category=category,
        symbol=symbol,
        votes=votes_fv,
        votes_value=votes_value,
        vote_share=vote_share_fv,
        vote_share_value=vote_share_value,
        votes_general=votes_general_fv,
        votes_general_value=votes_general_value,
        votes_postal=votes_postal_fv,
        votes_postal_value=votes_postal_value,
        total_electors=total_electors_fv,
        total_electors_value=total_electors_value,
        valid_votes=valid_votes_fv,
        valid_votes_value=valid_votes_value,
        total_votes_polled=total_votes_polled_fv,
        total_votes_polled_value=total_votes_polled_value,
        result_raw=None,
        result_normalized="UNKNOWN",
        rank=None,
        source_candidate_id=None,
        raw_row=raw_row,
        row_status=RowStatus.VALID,
    )


def parse_report33_sheet(
    sheet: ExtractedSheet,
    *,
    election_type: str = "LOK_SABHA",
    election_year: int = 2024,
) -> ParsedStatisticalReport:
    schema_status, semantic_lookup, warnings = fingerprint_headers(sheet.headers)
    rows: list[ParsedResultRow] = []

    if schema_status == SchemaFingerprintStatus.SCHEMA_UNSUPPORTED:
        return ParsedStatisticalReport(
            report_number=REPORT33_NUMBER,
            report_title=REPORT33_TITLE,
            election_type=election_type,
            election_year=election_year,
            sheet_name=sheet.name,
            schema_status=schema_status,
            parser_version=PARSER_VERSION,
            headers_observed=list(sheet.headers),
            rows=[],
            warnings=warnings + ["schema unsupported; no rows parsed"],
        )

    for extracted in sheet.rows:
        if _is_blank_row(extracted.raw_by_header):
            continue
        if _is_total_footer(extracted.raw_by_header, semantic_lookup):
            continue
        rows.append(
            _parse_data_row(
                sheet_name=sheet.name,
                source_row_number=extracted.source_row_number,
                raw_by_header=extracted.raw_by_header,
                semantic_lookup=semantic_lookup,
            )
        )

    rows = validate_parsed_rows(rows)
    coverage = build_coverage_report(rows, is_fixture_subset=True)

    return ParsedStatisticalReport(
        report_number=REPORT33_NUMBER,
        report_title=REPORT33_TITLE,
        election_type=election_type,
        election_year=election_year,
        sheet_name=sheet.name,
        schema_status=schema_status,
        parser_version=PARSER_VERSION,
        headers_observed=list(sheet.headers),
        rows=rows,
        coverage=coverage,
        warnings=warnings,
    )


def parse_report33_workbook(
    workbook: ExtractedWorkbook,
    *,
    election_type: str = "LOK_SABHA",
    election_year: int = 2024,
    sheet_name: str = REPORT33_SHEET_NAME,
) -> ParsedStatisticalReport:
    if workbook.format_status != WorkbookFormatStatus.WORKBOOK_SUPPORTED:
        return ParsedStatisticalReport(
            report_number=REPORT33_NUMBER,
            report_title=REPORT33_TITLE,
            election_type=election_type,
            election_year=election_year,
            sheet_name=sheet_name,
            schema_status=SchemaFingerprintStatus.SCHEMA_UNSUPPORTED,
            parser_version=PARSER_VERSION,
            warnings=[workbook.error or f"workbook status={workbook.format_status}"],
        )

    sheet = next((s for s in workbook.sheets if s.name == sheet_name), None)
    if sheet is None:
        names = [s.name for s in workbook.sheets]
        return ParsedStatisticalReport(
            report_number=REPORT33_NUMBER,
            report_title=REPORT33_TITLE,
            election_type=election_type,
            election_year=election_year,
            sheet_name=sheet_name,
            schema_status=SchemaFingerprintStatus.SCHEMA_UNSUPPORTED,
            parser_version=PARSER_VERSION,
            warnings=[f"sheet {sheet_name!r} not found; available={names}"],
        )
    return parse_report33_sheet(sheet, election_type=election_type, election_year=election_year)
