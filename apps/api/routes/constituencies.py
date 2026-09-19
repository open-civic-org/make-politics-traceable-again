from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from packages.db.models import OfficeTerm, ParliamentaryConstituency, Person
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from apps.api.deps import get_db

router = APIRouter(tags=["constituencies"])


class ConstituencyDetail(BaseModel):
    pc_id: str
    name: str
    state_name: str | None = None
    eci_code: str | None = None
    source_id: str | None = None
    current_mp_person_id: str | None = None
    current_mp_name: str | None = None


@router.get("/constituencies/{pc_id}", response_model=ConstituencyDetail)
def get_constituency(pc_id: str, db: Session = Depends(get_db)) -> ConstituencyDetail:
    pc = db.scalars(
        select(ParliamentaryConstituency)
        .options(joinedload(ParliamentaryConstituency.state))
        .where(ParliamentaryConstituency.pc_id == pc_id)
    ).first()
    if pc is None:
        raise HTTPException(status_code=404, detail="Constituency not found")

    term = db.scalars(
        select(OfficeTerm)
        .options(joinedload(OfficeTerm.person))
        .where(OfficeTerm.constituency_pc_id == pc_id, OfficeTerm.end_date.is_(None))
        .limit(1)
    ).first()

    person: Person | None = term.person if term else None
    return ConstituencyDetail(
        pc_id=pc.pc_id,
        name=pc.name,
        state_name=pc.state.name if pc.state else None,
        eci_code=pc.eci_code,
        source_id=pc.source_id,
        current_mp_person_id=person.person_id if person else None,
        current_mp_name=person.canonical_name if person else None,
    )
