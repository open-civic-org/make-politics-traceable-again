from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class ParsedCandidateResult(BaseModel):
    candidate_name: str
    party_name: str
    party_abbreviation: str | None = None
    votes: int
    vote_share_percent: Decimal | None = None
    rank: int | None = None
    result: str | None = None


class ParsedConstituency(BaseModel):
    name: str
    eci_constituency_code: str | None = None
    state_name: str
    state_code: str | None = None
    constituency_type: str = "PARLIAMENTARY"


class ParsedElection(BaseModel):
    election_type: str
    year: int
    election_date: date | None = None
    eci_election_id: str | None = None
    constituency: ParsedConstituency
    candidates: list[ParsedCandidateResult] = Field(default_factory=list)


class NormalizedCandidateResult(BaseModel):
    candidate_name_raw: str
    candidate_name_normalized: str
    party_name_raw: str
    party_name_normalized: str
    party_abbreviation: str | None = None
    votes: int
    vote_share: Decimal | None = None
    vote_share_derived: bool = False
    rank: int | None = None
    result: str | None = None


class NormalizedConstituency(BaseModel):
    name_raw: str
    name_normalized: str
    source_identifier: str | None = None
    state_name_raw: str
    state_name_normalized: str
    state_code: str | None = None
    constituency_type: str


class NormalizedElection(BaseModel):
    election_type: str
    election_year: int
    election_date: date | None = None
    source_election_id: str | None = None
    constituency: NormalizedConstituency
    candidates: list[NormalizedCandidateResult] = Field(default_factory=list)
