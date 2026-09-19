from __future__ import annotations

from packages.schemas.common import DeclaredValue, ProvenanceRef
from pydantic import BaseModel, Field


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
    education_declarations: list[DeclaredValue] = []
    profession_declarations: list[DeclaredValue] = []
    asset_declarations: list[DeclaredValue] = []
    liability_declarations: list[DeclaredValue] = []
    criminal_case_declarations: list[DeclaredValue] = []
    income_declarations: list[DeclaredValue] = []
    elections: list[ElectionRecord] = []
    sources: list[ProvenanceRef] = []
