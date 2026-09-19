from __future__ import annotations

from packages.schemas.common import DeclaredValue, ProvenanceRef
from pydantic import BaseModel, Field


class EducationDeclarationOut(BaseModel):
    """Declared education from an election affidavit (not independently verified)."""

    declared_value: str
    normalized_level: str | None = None
    institution_raw: str | None = None
    year_raw: str | None = None
    declaration_year: int | None = None
    verification_status: str = "SELF_DECLARED"
    source_id: str
    label: str = "Self-declared in election affidavit"


class FinancialDeclarationOut(BaseModel):
    """Declared assets/liabilities/income; amounts as strings to preserve Decimal precision."""

    category: str | None = None
    description: str
    amount_raw: str | None = None
    amount: str | None = Field(
        default=None,
        description="Normalized INR amount as a decimal string (never a JSON number)",
    )
    currency: str | None = "INR"
    declaration_year: int | None = None
    verification_status: str = "SELF_DECLARED"
    source_id: str
    label: str = "Self-declared in election affidavit"


class CaseDeclarationOut(BaseModel):
    """Declared criminal-case disclosure from Form 26 — not a legal determination."""

    case_summary: str
    case_number_raw: str | None = None
    court_raw: str | None = None
    act_raw: str | None = None
    section_raw: str | None = None
    status_raw: str | None = None
    normalized_status: str | None = None
    declaration_year: int | None = None
    verification_status: str = "SELF_DECLARED"
    source_id: str
    label: str = "Self-declared in election affidavit"


class PersonSummary(BaseModel):
    person_id: str
    canonical_name: str
    current_party_name: str | None = None
    current_office: str | None = None
    constituency_name: str | None = None
    state_name: str | None = None
    is_demo: bool = False


class PaginatedPeople(BaseModel):
    items: list[PersonSummary]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total: int = Field(ge=0)


class ElectionRecord(BaseModel):
    election_id: str
    year: int
    election_type: str
    constituency_name: str | None = None
    party_name: str | None = None
    candidate_name_as_published: str
    votes_received: int | None = None
    vote_share: str | None = None  # Decimal as string to avoid float rounding
    result: str | None = None
    rank: int | None = None
    source: ProvenanceRef


class PersonDetail(PersonSummary):
    aliases: list[str] = []
    photo_url: str | None = None
    education_declarations: list[EducationDeclarationOut] = []
    profession_declarations: list[DeclaredValue] = []
    asset_declarations: list[FinancialDeclarationOut] = []
    liability_declarations: list[FinancialDeclarationOut] = []
    criminal_case_declarations: list[CaseDeclarationOut] = []
    income_declarations: list[FinancialDeclarationOut] = []
    elections: list[ElectionRecord] = []
    sources: list[ProvenanceRef] = []
