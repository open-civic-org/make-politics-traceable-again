"""Row-level validation and Report 33 coverage contract."""

from __future__ import annotations

from collections import Counter

from collectors.eci.statistical_reports.schemas import (
    REPORT33_EXPECTED_PC_COUNT,
    CoverageReport,
    CoverageStatus,
    FieldStatus,
    ParsedResultRow,
    RowStatus,
)


def validate_row(row: ParsedResultRow) -> ParsedResultRow:
    """Classify VALID / PARTIAL / REJECTED without inventing winners or ranks."""
    reasons: list[str] = []

    required = (
        ("candidate_name", row.candidate_name),
        ("constituency_name", row.constituency_name),
        ("state", row.state),
        ("party_name", row.party_name),
    )
    missing_required = [name for name, fv in required if fv.status == FieldStatus.MISSING]
    invalid_required = [name for name, fv in required if fv.status == FieldStatus.INVALID]

    if missing_required or invalid_required:
        parts = []
        if missing_required:
            parts.append(f"missing={missing_required}")
        if invalid_required:
            parts.append(f"invalid={invalid_required}")
        row.row_status = RowStatus.REJECTED
        row.rejection_reason = "; ".join(parts)
        return row

    optional_numeric_invalid = []
    for name, fv in (
        ("votes", row.votes),
        ("vote_share", row.vote_share),
        ("votes_general", row.votes_general),
        ("votes_postal", row.votes_postal),
        ("total_electors", row.total_electors),
        ("valid_votes", row.valid_votes),
        ("total_votes_polled", row.total_votes_polled),
    ):
        if fv.status == FieldStatus.INVALID:
            optional_numeric_invalid.append(name)

    if row.votes.status == FieldStatus.MISSING or row.votes_value is None:
        reasons.append("votes missing")

    if optional_numeric_invalid:
        reasons.append(f"invalid_numeric={optional_numeric_invalid}")

    if reasons:
        row.row_status = RowStatus.PARTIAL
        row.rejection_reason = "; ".join(reasons)
    else:
        row.row_status = RowStatus.VALID
        row.rejection_reason = None

    # Never invent WON/LOST or rank.
    row.result_normalized = "UNKNOWN"
    row.rank = None
    return row


def flag_duplicate_source_rows(rows: list[ParsedResultRow]) -> list[ParsedResultRow]:
    """Flag duplicate (sheet, source_row_number) — should not occur from a single extract."""
    counts = Counter((r.sheet_name, r.source_row_number) for r in rows)
    for row in rows:
        if counts[(row.sheet_name, row.source_row_number)] > 1:
            if "DUPLICATE_SOURCE_ROW" not in row.flags:
                row.flags.append("DUPLICATE_SOURCE_ROW")
            if row.row_status == RowStatus.VALID:
                row.row_status = RowStatus.PARTIAL
            note = "DUPLICATE_SOURCE_ROW"
            row.rejection_reason = (
                f"{row.rejection_reason}; {note}" if row.rejection_reason else note
            )
    return rows


def validate_parsed_rows(rows: list[ParsedResultRow]) -> list[ParsedResultRow]:
    validated = [validate_row(r) for r in rows]
    return flag_duplicate_source_rows(validated)


def build_coverage_report(
    rows: list[ParsedResultRow],
    *,
    is_fixture_subset: bool = False,
    expected_pc_count: int = REPORT33_EXPECTED_PC_COUNT,
) -> CoverageReport:
    """
    Coverage contract documents 542 PCs as published in ECI Dec 2024 disclosure.

    Not a hard failure when the workbook (e.g. tiny fixture) has fewer constituencies.
    """
    pcs = {
        r.constituency_name.normalized
        for r in rows
        if r.constituency_name.normalized and r.row_status != RowStatus.REJECTED
    }
    observed = len(pcs)
    notes: list[str] = [
        f"expected_scope documents {expected_pc_count} parliamentary constituencies "
        "as published in ECI GE-2024 Statistical Report 33 (Dec 2024 disclosure)"
    ]

    if is_fixture_subset or observed < expected_pc_count:
        status = CoverageStatus.INCOMPLETE if observed > 0 else CoverageStatus.UNKNOWN
        if is_fixture_subset:
            notes.append("fixture_subset")
            # Tiny fixtures are not incomplete production captures — mark UNKNOWN.
            status = CoverageStatus.UNKNOWN
        else:
            notes.append(f"observed_pc_count={observed} < expected={expected_pc_count}")
    elif observed >= expected_pc_count:
        status = CoverageStatus.COMPLETE_AS_PUBLISHED
        notes.append(f"observed_pc_count={observed} meets published scope")
    else:
        status = CoverageStatus.UNKNOWN

    return CoverageReport(
        expected_scope=f"GE-2024 Report 33: {expected_pc_count} PCs as published",
        expected_pc_count=expected_pc_count,
        observed_pc_count=observed,
        observed_candidate_rows=len(rows),
        coverage_status=status,
        notes=notes,
    )
