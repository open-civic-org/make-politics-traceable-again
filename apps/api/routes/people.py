from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from packages.db.models import (
    Affidavit,
    Candidacy,
    Election,
    ElectionResult,
    OfficeTerm,
    Person,
    PersonAlias,
    SourceDocument,
)
from packages.schemas.common import DeclaredValue, ProvenanceRef
from packages.schemas.people import ElectionRecord, PaginatedPeople, PersonDetail, PersonSummary
from packages.shared.ids import normalize_name
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from apps.api.deps import get_db

router = APIRouter(tags=["people"])

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100


def _provenance(source: SourceDocument | None, fallback_id: str | None = None) -> ProvenanceRef:
    if source is not None:
        return ProvenanceRef(
            source_id=source.source_id,
            source_authority=source.source_authority,
            source_url=source.source_url,
            verification_status=source.verification_status,
        )
    if fallback_id:
        return ProvenanceRef(source_id=fallback_id)
    raise ValueError("source required")


def _declared(value: str, year: int | None, source_id: str) -> DeclaredValue:
    return DeclaredValue(
        value=value,
        declaration_year=year,
        source_id=source_id,
        verification_status="SELF_DECLARED",
    )


@router.get("/people", response_model=PaginatedPeople)
def list_people(
    q: str | None = Query(default=None, description="Search by name or alias"),
    page: int = Query(default=1, ge=1, description="1-based page number"),
    page_size: int = Query(
        default=DEFAULT_PAGE_SIZE,
        ge=1,
        le=MAX_PAGE_SIZE,
        description=f"Results per page (default {DEFAULT_PAGE_SIZE}, max {MAX_PAGE_SIZE})",
    ),
    db: Session = Depends(get_db),
) -> PaginatedPeople:
    filters = []
    if q:
        needle = normalize_name(q)
        alias_ids = select(PersonAlias.person_id).where(PersonAlias.alias.ilike(f"%{q}%"))
        filters.append(
            or_(
                Person.normalized_name.contains(needle),
                Person.canonical_name.ilike(f"%{q}%"),
                Person.person_id.in_(alias_ids),
            )
        )

    count_stmt = select(func.count()).select_from(Person)
    if filters:
        count_stmt = count_stmt.where(*filters)
    total = int(db.scalar(count_stmt) or 0)

    stmt = (
        select(Person)
        .options(joinedload(Person.current_party))
        .order_by(Person.canonical_name.asc(), Person.person_id.asc())
    )
    if filters:
        stmt = stmt.where(*filters)
    offset = (page - 1) * page_size
    people = db.scalars(stmt.offset(offset).limit(page_size)).unique().all()

    results: list[PersonSummary] = []
    for person in people:
        term = db.scalars(
            select(OfficeTerm)
            .options(joinedload(OfficeTerm.constituency), joinedload(OfficeTerm.state))
            .where(OfficeTerm.person_id == person.person_id, OfficeTerm.end_date.is_(None))
            .limit(1)
        ).first()
        results.append(
            PersonSummary(
                person_id=person.person_id,
                canonical_name=person.canonical_name,
                current_party_name=person.current_party.name if person.current_party else None,
                current_office=person.current_office,
                constituency_name=term.constituency.name if term and term.constituency else None,
                state_name=term.state.name if term and term.state else None,
                is_demo=person.is_demo,
            )
        )
    return PaginatedPeople(items=results, page=page, page_size=page_size, total=total)


@router.get("/people/{person_id}", response_model=PersonDetail)
def get_person(person_id: str, db: Session = Depends(get_db)) -> PersonDetail:
    person = db.scalars(
        select(Person)
        .options(joinedload(Person.current_party), selectinload(Person.aliases))
        .where(Person.person_id == person_id)
    ).first()
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")

    term = db.scalars(
        select(OfficeTerm)
        .options(
            joinedload(OfficeTerm.constituency),
            joinedload(OfficeTerm.state),
            joinedload(OfficeTerm.source),
        )
        .where(OfficeTerm.person_id == person_id, OfficeTerm.end_date.is_(None))
        .limit(1)
    ).first()

    affidavits = (
        db.scalars(
            select(Affidavit)
            .options(
                selectinload(Affidavit.education_declarations),
                selectinload(Affidavit.profession_declarations),
                selectinload(Affidavit.asset_declarations),
                selectinload(Affidavit.liability_declarations),
                selectinload(Affidavit.criminal_case_declarations),
                selectinload(Affidavit.income_declarations),
                joinedload(Affidavit.election),
                joinedload(Affidavit.source),
            )
            .where(Affidavit.person_id == person_id)
        )
        .unique()
        .all()
    )

    candidacies = (
        db.scalars(
            select(Candidacy)
            .options(
                joinedload(Candidacy.election).joinedload(Election.constituency),
                joinedload(Candidacy.party),
                joinedload(Candidacy.result).joinedload(ElectionResult.source),
                joinedload(Candidacy.source),
            )
            .where(Candidacy.person_id == person_id)
        )
        .unique()
        .all()
    )

    education: list[DeclaredValue] = []
    profession: list[DeclaredValue] = []
    assets: list[DeclaredValue] = []
    liabilities: list[DeclaredValue] = []
    cases: list[DeclaredValue] = []
    income: list[DeclaredValue] = []
    sources: dict[str, ProvenanceRef] = {}

    for aff in affidavits:
        year = aff.election.year if aff.election else None
        if aff.source:
            sources[aff.source.source_id] = _provenance(aff.source)
        for d in aff.education_declarations:
            education.append(_declared(d.declared_education, year, d.source_id))
        for d in aff.profession_declarations:
            profession.append(_declared(d.declared_profession, year, d.source_id))
        for d in aff.asset_declarations:
            val = f"{d.asset_category}: {d.description}"
            if d.declared_value_inr is not None:
                val += f" (₹{d.declared_value_inr})"
            assets.append(_declared(val, year, d.source_id))
        for d in aff.liability_declarations:
            val = d.description
            if d.declared_value_inr is not None:
                val += f" (₹{d.declared_value_inr})"
            liabilities.append(_declared(val, year, d.source_id))
        for d in aff.criminal_case_declarations:
            cases.append(_declared(f"[{d.disposition}] {d.case_summary}", year, d.source_id))
        for d in aff.income_declarations:
            val = d.description
            if d.declared_value_inr is not None:
                val += f" (₹{d.declared_value_inr})"
            income.append(_declared(val, year, d.source_id))

    elections: list[ElectionRecord] = []
    for c in candidacies:
        src = c.result.source if c.result and c.result.source else c.source
        sources[src.source_id] = _provenance(src)
        elections.append(
            ElectionRecord(
                election_id=c.election.election_id,
                year=c.election.year,
                election_type=c.election.election_type,
                constituency_name=c.election.constituency.name if c.election.constituency else None,
                party_name=c.party.name if c.party else None,
                candidate_name_as_published=c.candidate_name_as_published,
                votes_received=int(c.result.votes_received)
                if c.result and c.result.votes_received is not None
                else None,
                vote_share=format(c.result.vote_share, "f")
                if c.result and c.result.vote_share is not None
                else None,
                result=c.result.result if c.result else None,
                rank=c.result.rank if c.result else None,
                source=_provenance(src),
            )
        )

    if term and term.source:
        sources[term.source.source_id] = _provenance(term.source)

    return PersonDetail(
        person_id=person.person_id,
        canonical_name=person.canonical_name,
        current_party_name=person.current_party.name if person.current_party else None,
        current_office=person.current_office,
        constituency_name=term.constituency.name if term and term.constituency else None,
        state_name=term.state.name if term and term.state else None,
        is_demo=person.is_demo,
        aliases=[a.alias for a in person.aliases],
        photo_url=person.photo_url,
        education_declarations=education,
        profession_declarations=profession,
        asset_declarations=assets,
        liability_declarations=liabilities,
        criminal_case_declarations=cases,
        income_declarations=income,
        elections=elections,
        sources=list(sources.values()),
    )
