from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from packages.db.models import Party
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.deps import get_db

router = APIRouter(tags=["parties"])


class PartyDetail(BaseModel):
    party_id: str
    name: str
    abbreviation: str | None = None
    official_name: str | None = None
    registration_status: str | None = None
    source_id: str | None = None


@router.get("/parties/{party_id}", response_model=PartyDetail)
def get_party(party_id: str, db: Session = Depends(get_db)) -> PartyDetail:
    party = db.scalars(select(Party).where(Party.party_id == party_id)).first()
    if party is None:
        raise HTTPException(status_code=404, detail="Party not found")
    return PartyDetail(
        party_id=party.party_id,
        name=party.name,
        abbreviation=party.abbreviation,
        official_name=party.official_name,
        registration_status=party.registration_status,
        source_id=party.source_id,
    )
