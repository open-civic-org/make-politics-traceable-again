"""Identity resolution helpers: external source IDs ↔ candidacy (never Person PK)."""

from __future__ import annotations

from packages.db.models import Candidacy, CandidacySourceIdentifier, Election, Person
from packages.shared.ids import IdPrefix, allocate_id
from sqlalchemy import select
from sqlalchemy.orm import Session

SOURCE_AUTHORITY_ECI = "Election Commission of India"
SOURCE_SYSTEM_RESULTS = "RESULTS_PORTAL"
SOURCE_SYSTEM_AFFIDAVIT = "AFFIDAVIT_PORTAL"
IDENTIFIER_TYPE_CANDIDATE_ID = "CANDIDATE_ID"
IDENTIFIER_TYPE_CANDIDATE_LOCATOR = "CANDIDATE_LOCATOR"
IDENTIFIER_TYPE_NOMINATION_ID = "NOMINATION_ID"


def _next_seq(session: Session, model, id_attr: str) -> int:
    ids = list(session.scalars(select(getattr(model, id_attr))).all())
    for obj in session.new:
        if isinstance(obj, model):
            ids.append(getattr(obj, id_attr))
    max_n = 0
    for raw in ids:
        try:
            max_n = max(max_n, int(str(raw).rsplit("-", 1)[-1]))
        except ValueError:
            continue
    return max_n + 1


def lookup_candidacy_by_external_id(
    session: Session,
    *,
    external_value_raw: str,
    election_id: str | None = None,
    source_authority: str = SOURCE_AUTHORITY_ECI,
    source_system: str | None = None,
    identifier_type: str = IDENTIFIER_TYPE_CANDIDATE_ID,
) -> Candidacy | None:
    """
    Resolve an external source identifier to a Candidacy.

    Never treats the external value as a Person primary key.
    When election_id is omitted, at most one match across elections is allowed;
    ambiguity returns None (caller should review).
    """
    value = external_value_raw.strip()
    if not value:
        return None

    stmt = select(CandidacySourceIdentifier).where(
        CandidacySourceIdentifier.source_authority == source_authority,
        CandidacySourceIdentifier.identifier_type == identifier_type,
        CandidacySourceIdentifier.external_value_raw == value,
    )
    if election_id is not None:
        stmt = stmt.where(CandidacySourceIdentifier.election_id == election_id)
    if source_system is not None:
        stmt = stmt.where(CandidacySourceIdentifier.source_system == source_system)

    rows = session.scalars(stmt).all()
    if len(rows) != 1:
        return None
    return session.get(Candidacy, rows[0].candidacy_id)


def attach_candidacy_source_identifier(
    session: Session,
    *,
    candidacy: Candidacy,
    election: Election,
    source_id: str,
    external_value_raw: str,
    source_system: str,
    identifier_type: str = IDENTIFIER_TYPE_CANDIDATE_ID,
    source_authority: str = SOURCE_AUTHORITY_ECI,
) -> CandidacySourceIdentifier | None:
    """
    Persist an external identifier for a candidacy.

    Returns None if external_value_raw is blank (never invent identifiers).
    Idempotent when the same scoped key already exists for this candidacy.
    Raises ValueError if the scoped key is already bound to a different candidacy.
    """
    value = (external_value_raw or "").strip()
    if not value:
        return None

    existing = session.scalars(
        select(CandidacySourceIdentifier).where(
            CandidacySourceIdentifier.source_authority == source_authority,
            CandidacySourceIdentifier.source_system == source_system,
            CandidacySourceIdentifier.identifier_type == identifier_type,
            CandidacySourceIdentifier.external_value_raw == value,
            CandidacySourceIdentifier.election_id == election.election_id,
        )
    ).first()
    if existing is not None:
        if existing.candidacy_id != candidacy.candidacy_id:
            raise ValueError(
                "external identifier already mapped to a different candidacy in this election scope"
            )
        return existing

    row = CandidacySourceIdentifier(
        identifier_id=allocate_id(
            IdPrefix.CANDIDACY_SOURCE_ID,
            _next_seq(session, CandidacySourceIdentifier, "identifier_id"),
        ),
        candidacy_id=candidacy.candidacy_id,
        election_id=election.election_id,
        source_authority=source_authority,
        source_system=source_system,
        identifier_type=identifier_type,
        external_value_raw=value,
        source_id=source_id,
    )
    session.add(row)
    session.flush()
    return row


def person_for_candidacy(session: Session, candidacy: Candidacy) -> Person | None:
    return session.get(Person, candidacy.person_id)
