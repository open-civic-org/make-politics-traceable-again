"""Schemas and version constants for ECI statistical report staging."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

COLLECTOR_NAME = "eci_statistical_reports"
COLLECTOR_VERSION = "ECI_STAT_REPORT_COLLECTOR_V1"
PARSER_VERSION = "ECI_LS2024_REPORT33_PARSER_V1"

REPORT33_NUMBER = "33"
REPORT33_TITLE = "Constituency Wise Detailed Result"
REPORT33_SHEET_NAME = "Detailed Results"
# Published scope for GE-2024 Report 33 (ECI Dec 2024 disclosure). Not a hard fail gate.
REPORT33_EXPECTED_PC_COUNT = 542


class FieldStatus(StrEnum):
    EXACT = "EXACT"
    NORMALIZED = "NORMALIZED"
    MISSING = "MISSING"
    INVALID = "INVALID"


class WorkbookFormatStatus(StrEnum):
    WORKBOOK_SUPPORTED = "WORKBOOK_SUPPORTED"
    FORMAT_MISMATCH = "FORMAT_MISMATCH"
    UNSUPPORTED = "UNSUPPORTED"
    CORRUPT = "CORRUPT"


class SchemaFingerprintStatus(StrEnum):
    SCHEMA_MATCH = "SCHEMA_MATCH"
    SCHEMA_CHANGED = "SCHEMA_CHANGED"
    SCHEMA_UNSUPPORTED = "SCHEMA_UNSUPPORTED"


class IdentityStatus(StrEnum):
    UNRESOLVED = "UNRESOLVED"
    EXACT_LINKED = "EXACT_LINKED"
    AMBIGUOUS = "AMBIGUOUS"
    CONFLICT = "CONFLICT"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class RowStatus(StrEnum):
    VALID = "VALID"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"


class CoverageStatus(StrEnum):
    COMPLETE_AS_PUBLISHED = "COMPLETE_AS_PUBLISHED"
    INCOMPLETE = "INCOMPLETE"
    UNKNOWN = "UNKNOWN"


class FieldValue(BaseModel):
    raw: str | None = None
    normalized: str | None = None
    status: FieldStatus = FieldStatus.MISSING


class ExtractedCell(BaseModel):
    column_index: int
    header: str | None = None
    raw_value: str | None = None
    value_type: str = "empty"


class ExtractedRow(BaseModel):
    sheet_name: str
    source_row_number: int
    cells: list[ExtractedCell] = Field(default_factory=list)
    raw_by_header: dict[str, str | None] = Field(default_factory=dict)


class ExtractedSheet(BaseModel):
    name: str
    headers: list[str] = Field(default_factory=list)
    rows: list[ExtractedRow] = Field(default_factory=list)


class ExtractedWorkbook(BaseModel):
    format_status: WorkbookFormatStatus
    detected_format: str | None = None
    sheet_count: int = 0
    sheets: list[ExtractedSheet] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None


class ParsedResultRow(BaseModel):
    sheet_name: str
    source_row_number: int
    state: FieldValue
    constituency_number: FieldValue
    constituency_name: FieldValue
    candidate_name: FieldValue
    party_name: FieldValue
    gender: FieldValue
    age: FieldValue
    category: FieldValue
    symbol: FieldValue
    votes: FieldValue
    votes_value: int | None = None
    vote_share: FieldValue
    vote_share_value: Decimal | None = None
    votes_general: FieldValue
    votes_general_value: int | None = None
    votes_postal: FieldValue
    votes_postal_value: int | None = None
    total_electors: FieldValue
    total_electors_value: int | None = None
    valid_votes: FieldValue
    valid_votes_value: int | None = None
    total_votes_polled: FieldValue
    total_votes_polled_value: int | None = None
    result_raw: str | None = None
    result_normalized: str = "UNKNOWN"
    rank: int | None = None
    source_candidate_id: str | None = None
    raw_row: dict[str, Any] = Field(default_factory=dict)
    row_status: RowStatus = RowStatus.VALID
    rejection_reason: str | None = None
    identity_status: IdentityStatus = IdentityStatus.UNRESOLVED
    identity_candidacy_id: str | None = None
    identity_notes: str | None = None
    flags: list[str] = Field(default_factory=list)


class CoverageReport(BaseModel):
    expected_scope: str
    expected_pc_count: int | None = None
    observed_pc_count: int = 0
    observed_candidate_rows: int = 0
    coverage_status: CoverageStatus = CoverageStatus.UNKNOWN
    notes: list[str] = Field(default_factory=list)


class ParsedStatisticalReport(BaseModel):
    report_number: str
    report_title: str
    election_type: str
    election_year: int
    sheet_name: str
    schema_status: SchemaFingerprintStatus
    parser_version: str = PARSER_VERSION
    headers_observed: list[str] = Field(default_factory=list)
    rows: list[ParsedResultRow] = Field(default_factory=list)
    coverage: CoverageReport | None = None
    warnings: list[str] = Field(default_factory=list)
