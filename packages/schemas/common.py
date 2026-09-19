from __future__ import annotations

from pydantic import BaseModel, Field


class ProvenanceRef(BaseModel):
    source_id: str
    source_authority: str | None = None
    source_url: str | None = None
    verification_status: str | None = None


class DeclaredValue(BaseModel):
    """A value taken from a declaration (e.g. election affidavit), not independently verified."""

    value: str
    declaration_year: int | None = None
    source_id: str
    verification_status: str = Field(
        default="SELF_DECLARED",
        description="SELF_DECLARED unless independently verified later",
    )
    label: str = Field(
        default="Self-declared in election affidavit",
        description="Display label clarifying declaration vs verification",
    )
