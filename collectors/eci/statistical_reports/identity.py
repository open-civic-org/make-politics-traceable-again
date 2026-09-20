"""Read-only identity reconciliation for statistical report staging rows.

NEVER creates Person / Candidacy / ElectionResult.
"""

from __future__ import annotations

from collectors.eci.statistical_reports.normalize import normalize_name
from collectors.eci.statistical_reports.schemas import IdentityStatus, ParsedResultRow
from packages.db.models import Candidacy, Election, ParliamentaryConstituency, Party, Person
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload


def reconcile_row_identity(
    session: Session,
    row: ParsedResultRow,
    *,
    election_year: int,
    election_type: str,
) -> ParsedResultRow:
    """
    Exact match only: normalized candidate name + election year + type + constituency name.

    EXACT_LINKED if exactly one candidacy; AMBIGUOUS if >1; UNRESOLVED if 0.
    CONFLICT if linked candidacy party name conflicts with the staging party.
    """
    cand_norm = row.candidate_name.normalized
    pc_norm = row.constituency_name.normalized
    if not cand_norm or not pc_norm:
        row.identity_status = IdentityStatus.UNRESOLVED
        row.identity_candidacy_id = None
        row.identity_notes = "missing candidate or constituency normalized name"
        return row

    stmt = (
        select(Candidacy)
        .join(Person, Candidacy.person_id == Person.person_id)
        .join(Election, Candidacy.election_id == Election.election_id)
        .outerjoin(
            ParliamentaryConstituency,
            Election.constituency_pc_id == ParliamentaryConstituency.pc_id,
        )
        .options(joinedload(Candidacy.party), joinedload(Candidacy.person))
        .where(
            Person.normalized_name == cand_norm,
            Election.year == election_year,
            Election.election_type == election_type,
        )
    )
    candidates = list(session.scalars(stmt).unique().all())

    # Filter by constituency name exact normalize match.
    matched: list[Candidacy] = []
    for cnd in candidates:
        election = session.get(Election, cnd.election_id)
        if election is None or election.constituency_pc_id is None:
            continue
        pc = session.get(ParliamentaryConstituency, election.constituency_pc_id)
        if pc is None:
            continue
        if normalize_name(pc.name) == pc_norm:
            matched.append(cnd)

    if len(matched) == 0:
        row.identity_status = IdentityStatus.UNRESOLVED
        row.identity_candidacy_id = None
        row.identity_notes = "no exact candidacy match"
        return row

    if len(matched) > 1:
        row.identity_status = IdentityStatus.AMBIGUOUS
        row.identity_candidacy_id = None
        row.identity_notes = f"ambiguous candidacy matches={len(matched)}"
        return row

    cnd = matched[0]
    row.identity_candidacy_id = cnd.candidacy_id
    party_norm = row.party_name.normalized
    if party_norm and cnd.party_id:
        party = session.get(Party, cnd.party_id)
        if party is not None and normalize_name(party.name) != party_norm:
            row.identity_status = IdentityStatus.CONFLICT
            row.identity_notes = (
                f"party conflict: staging={party_norm!r} linked={normalize_name(party.name)!r}"
            )
            return row

    row.identity_status = IdentityStatus.EXACT_LINKED
    row.identity_notes = None
    return row


def reconcile_report_identity(
    session: Session,
    rows: list[ParsedResultRow],
    *,
    election_year: int,
    election_type: str,
) -> list[ParsedResultRow]:
    return [
        reconcile_row_identity(
            session, row, election_year=election_year, election_type=election_type
        )
        for row in rows
    ]
