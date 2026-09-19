from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field

PARSER_VERSION = "ECI_AFFIDAVIT_PARSER_V1"
COLLECTOR_VERSION = "0.1.0"
COLLECTOR_NAME = "eci_affidavits"


class ExtractionStatus(StrEnum):
    TEXT_EXTRACTED = "TEXT_EXTRACTED"
    OCR_REQUIRED = "OCR_REQUIRED"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"


class FieldStatus(StrEnum):
    EXACT = "EXACT"
    NORMALIZED = "NORMALIZED"
    AMBIGUOUS = "AMBIGUOUS"
    MISSING = "MISSING"
    PARSE_FAILED = "PARSE_FAILED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class ParseOutcome(StrEnum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    IDENTITY_REVIEW_REQUIRED = "IDENTITY_REVIEW_REQUIRED"
    SOURCE_CHANGED = "SOURCE_CHANGED"
    UNCHANGED = "UNCHANGED"


class EducationLevel(StrEnum):
    NO_FORMAL_EDUCATION = "NO_FORMAL_EDUCATION"
    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"
    HIGHER_SECONDARY = "HIGHER_SECONDARY"
    DIPLOMA = "DIPLOMA"
    GRADUATE = "GRADUATE"
    POSTGRADUATE = "POSTGRADUATE"
    DOCTORATE = "DOCTORATE"
    PROFESSIONAL = "PROFESSIONAL"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class CaseStatus(StrEnum):
    DECLARED_PENDING_CASE = "DECLARED_PENDING_CASE"
    CHARGE_FRAMED = "CHARGE_FRAMED"
    CONVICTION = "CONVICTION"
    ACQUITTAL = "ACQUITTAL"
    DISMISSED = "DISMISSED"
    APPEAL = "APPEAL"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class TextBlock(BaseModel):
    page_number: int
    text: str
    line_number: int | None = None


class ExtractedDocument(BaseModel):
    extraction_status: ExtractionStatus
    extraction_method: str
    pages: list[TextBlock] = Field(default_factory=list)
    full_text: str = ""
    warnings: list[str] = Field(default_factory=list)


class ParsedEducation(BaseModel):
    declared_value_raw: str
    institution_raw: str | None = None
    year_raw: str | None = None
    field_status: FieldStatus = FieldStatus.EXACT
    page_number: int | None = None


class ParsedAsset(BaseModel):
    asset_category: str
    description: str
    amount_raw: str | None = None
    field_status: FieldStatus = FieldStatus.EXACT
    page_number: int | None = None


class ParsedLiability(BaseModel):
    description: str
    amount_raw: str | None = None
    field_status: FieldStatus = FieldStatus.EXACT
    page_number: int | None = None


class ParsedCaseDeclaration(BaseModel):
    case_summary: str
    case_number_raw: str | None = None
    court_raw: str | None = None
    act_raw: str | None = None
    section_raw: str | None = None
    status_raw: str | None = None
    date_raw: str | None = None
    field_status: FieldStatus = FieldStatus.EXACT
    page_number: int | None = None


class ParsedProfession(BaseModel):
    declared_value_raw: str
    field_status: FieldStatus = FieldStatus.EXACT


class ParsedIncome(BaseModel):
    description: str
    amount_raw: str | None = None
    assessment_year: str | None = None
    field_status: FieldStatus = FieldStatus.EXACT


class ParsedAffidavit(BaseModel):
    candidate_name_raw: str
    constituency_name_raw: str | None = None
    state_name_raw: str | None = None
    election_year: int | None = None
    election_type: str | None = None
    source_candidate_id: str | None = None
    education: list[ParsedEducation] = Field(default_factory=list)
    profession: list[ParsedProfession] = Field(default_factory=list)
    assets: list[ParsedAsset] = Field(default_factory=list)
    liabilities: list[ParsedLiability] = Field(default_factory=list)
    cases: list[ParsedCaseDeclaration] = Field(default_factory=list)
    income: list[ParsedIncome] = Field(default_factory=list)
    section_status: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class NormalizedEducation(BaseModel):
    declared_value_raw: str
    normalized_level: EducationLevel
    institution_raw: str | None = None
    year_raw: str | None = None
    field_status: FieldStatus
    page_number: int | None = None


class NormalizedAsset(BaseModel):
    asset_category: str
    description: str
    amount_raw: str | None
    amount_value: Decimal | None
    currency: str = "INR"
    field_status: FieldStatus
    is_derived: bool = False
    page_number: int | None = None


class NormalizedLiability(BaseModel):
    description: str
    amount_raw: str | None
    amount_value: Decimal | None
    currency: str = "INR"
    field_status: FieldStatus
    is_derived: bool = False
    page_number: int | None = None


class NormalizedCaseDeclaration(BaseModel):
    case_summary: str
    case_number_raw: str | None = None
    court_raw: str | None = None
    act_raw: str | None = None
    section_raw: str | None = None
    status_raw: str | None = None
    normalized_status: CaseStatus
    date_raw: str | None = None
    field_status: FieldStatus
    page_number: int | None = None


class NormalizedProfession(BaseModel):
    declared_value_raw: str
    field_status: FieldStatus


class NormalizedIncome(BaseModel):
    description: str
    amount_raw: str | None
    amount_value: Decimal | None
    currency: str = "INR"
    assessment_year: str | None
    field_status: FieldStatus


class NormalizedAffidavit(BaseModel):
    candidate_name_raw: str
    candidate_name_normalized: str
    constituency_name_raw: str | None = None
    constituency_name_normalized: str | None = None
    state_name_raw: str | None = None
    state_name_normalized: str | None = None
    election_year: int | None = None
    election_type: str | None = None
    source_candidate_id: str | None = None
    education: list[NormalizedEducation] = Field(default_factory=list)
    profession: list[NormalizedProfession] = Field(default_factory=list)
    assets: list[NormalizedAsset] = Field(default_factory=list)
    liabilities: list[NormalizedLiability] = Field(default_factory=list)
    cases: list[NormalizedCaseDeclaration] = Field(default_factory=list)
    income: list[NormalizedIncome] = Field(default_factory=list)
    section_status: dict[str, str] = Field(default_factory=dict)
    parse_outcome: ParseOutcome = ParseOutcome.SUCCESS
    warnings: list[str] = Field(default_factory=list)


class ReviewItemDraft(BaseModel):
    review_type: str
    field: str | None = None
    reason: str
    raw_text: str | None = None
    page_number: int | None = None
