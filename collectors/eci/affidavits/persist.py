"""Persist normalized affidavits with required candidacy linkage and review queue."""

from __future__ import annotations

from collectors.base.artifacts import ArchivedArtifact
from collectors.base.collector import RunStats
from collectors.eci.affidavits.schemas import (
    COLLECTOR_NAME,
    PARSER_VERSION,
    FieldStatus,
    NormalizedAffidavit,
    ParseOutcome,
    ReviewItemDraft,
)
from packages.db.models import (
    Affidavit,
    AssetDeclaration,
    Candidacy,
    CriminalCaseDeclaration,
    EducationDeclaration,
    Election,
    IncomeDeclaration,
    LiabilityDeclaration,
    ParliamentaryConstituency,
    Person,
    ProfessionDeclaration,
    ReviewItem,
    SourceDocument,
)
from packages.shared.ids import IdPrefix, allocate_id, normalize_name
from sqlalchemy import select
from sqlalchemy.orm import Session

_REVIEWABLE_FIELD_STATUSES = {
    FieldStatus.PARSE_FAILED,
    FieldStatus.AMBIGUOUS,
    FieldStatus.NEEDS_REVIEW,
}


class LinkageError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        Exception.__init__(self, message)


def _next_seq(session: Session, model, id_attr: str) -> int:
    ids = list(session.scalars(select(getattr(model, id_attr))).all())
    # Include pending inserts not yet flushed
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


def resolve_person_and_election(
    session: Session, normalized: NormalizedAffidavit
) -> tuple[Person, Election, Candidacy]:
    """
    Link affidavit to Person + Election + Candidacy via exact controlled match only.

    Preferred: external ECI candidate identifier → candidacy_source_identifier → Candidacy.
    Fallback: exact normalized name + election year/type/constituency when exactly one match.
    Never treats an external ECI ID as a Person primary key.
    """
    from packages.shared.identity import (
        IDENTIFIER_TYPE_CANDIDATE_ID,
        SOURCE_AUTHORITY_ECI,
        lookup_candidacy_by_external_id,
        person_for_candidacy,
    )

    if normalized.source_candidate_id:
        ext = normalized.source_candidate_id.strip()
        # Reject treating IND-PER-* style internal IDs as external ECI identifiers.
        if ext.upper().startswith("IND-PER-"):
            raise LinkageError(
                "IDENTITY_REVIEW_REQUIRED",
                "source_candidate_id looks like an internal person_id; use external ECI identifier",
            )
        candidacy = lookup_candidacy_by_external_id(
            session,
            external_value_raw=ext,
            source_authority=SOURCE_AUTHORITY_ECI,
            identifier_type=IDENTIFIER_TYPE_CANDIDATE_ID,
        )
        if candidacy is not None:
            election = session.get(Election, candidacy.election_id)
            person = person_for_candidacy(session, candidacy)
            if election is None or person is None:
                raise LinkageError(
                    "IDENTITY_REVIEW_REQUIRED",
                    "external candidate identifier mapped but election/person missing",
                )
            # When affidavit also supplies year/type/constituency, they must agree.
            if not _election_matches_affidavit(session, election, normalized):
                raise LinkageError(
                    "IDENTITY_REVIEW_REQUIRED",
                    "external candidate identifier resolved to a candidacy that conflicts "
                    "with affidavit election/constituency fields",
                )
            return person, election, candidacy
        # Unknown external ID — fall through to controlled name matching (may still fail)

    matches = session.scalars(
        select(Person).where(Person.normalized_name == normalized.candidate_name_normalized)
    ).all()
    if len(matches) == 0:
        raise LinkageError("IDENTITY_REVIEW_REQUIRED", "no person match for candidate name")
    if len(matches) > 1:
        narrowed = _narrow_by_election(session, matches, normalized)
        if narrowed is None:
            raise LinkageError(
                "IDENTITY_REVIEW_REQUIRED",
                (
                    f"ambiguous person match ({len(matches)}) "
                    f"for {normalized.candidate_name_raw!r}"
                ),
            )
        return narrowed
    person = matches[0]

    election, candidacy = _find_election_candidacy(session, person, normalized)
    if election is None or candidacy is None:
        raise LinkageError(
            "IDENTITY_REVIEW_REQUIRED",
            "person matched but election/candidacy could not be uniquely resolved",
        )
    return person, election, candidacy


def _election_matches_affidavit(
    session: Session, election: Election, normalized: NormalizedAffidavit
) -> bool:
    if normalized.election_year is not None and election.year != normalized.election_year:
        return False
    if normalized.election_type is not None:
        if election.election_type.upper() != normalized.election_type.strip().upper():
            return False
    if normalized.constituency_name_normalized:
        if not election.constituency_pc_id:
            return False
        pc = session.get(ParliamentaryConstituency, election.constituency_pc_id)
        if pc is None or normalize_name(pc.name) != normalized.constituency_name_normalized:
            return False
    return True


def _narrow_by_election(
    session: Session, people: list[Person], normalized: NormalizedAffidavit
) -> tuple[Person, Election, Candidacy] | None:
    if not normalized.election_year or not normalized.constituency_name_normalized:
        return None
    hits: list[tuple[Person, Election, Candidacy]] = []
    for person in people:
        election, candidacy = _find_election_candidacy(session, person, normalized)
        if election and candidacy:
            hits.append((person, election, candidacy))
    if len(hits) == 1:
        return hits[0]
    return None


def _find_election_candidacy(
    session: Session, person: Person, normalized: NormalizedAffidavit
) -> tuple[Election | None, Candidacy | None]:
    candidacies = session.scalars(
        select(Candidacy).where(Candidacy.person_id == person.person_id)
    ).all()
    if not candidacies:
        return None, None

    matched: list[tuple[Election, Candidacy]] = []
    for c in candidacies:
        el = session.get(Election, c.election_id)
        if el is None:
            continue
        if normalized.election_year is not None and el.year != normalized.election_year:
            continue
        if normalized.election_type is not None:
            if el.election_type.upper() != normalized.election_type.strip().upper():
                continue
        if normalized.constituency_name_normalized:
            # Affidavit supplied a constituency — election must have a matching one.
            if not el.constituency_pc_id:
                continue
            pc = session.get(ParliamentaryConstituency, el.constituency_pc_id)
            if pc is None or normalize_name(pc.name) != normalized.constituency_name_normalized:
                continue
        matched.append((el, c))

    if len(matched) == 1:
        return matched[0]
    return None, None


def get_or_create_source(
    session: Session,
    artifact: ArchivedArtifact,
    stats: RunStats,
    *,
    extraction_method: str,
) -> tuple[SourceDocument, str]:
    """Return (source, status) where status is INSERTED | UNCHANGED | SOURCE_CHANGED."""
    existing_same = session.scalars(
        select(SourceDocument).where(SourceDocument.content_sha256 == artifact.sha256)
    ).first()
    if existing_same:
        stats.records_unchanged += 1
        return existing_same, "UNCHANGED"

    # Same archived_path / URL with different hash → SOURCE_CHANGED observation
    prior = session.scalars(
        select(SourceDocument).where(SourceDocument.source_url == artifact.source_url)
    ).first()
    status = "SOURCE_CHANGED" if prior else "INSERTED"

    source = SourceDocument(
        source_id=allocate_id(IdPrefix.SOURCE, _next_seq(session, SourceDocument, "source_id")),
        source_authority="Election Commission of India",
        source_type="CANDIDATE_AFFIDAVIT",
        source_url=artifact.source_url,
        document_title=f"ECI affidavit {artifact.artifact_id}",
        retrieved_at=artifact.retrieved_at,
        content_sha256=artifact.sha256,
        archived_path=str(artifact.archive_dir),
        collector_name=COLLECTOR_NAME,
        collector_version=artifact.collector_version,
        parser_version=PARSER_VERSION,
        git_commit_sha=artifact.git_commit_sha,
        extraction_method=extraction_method,
        extraction_confidence=None,
        verification_status="UNVERIFIED",
    )
    session.add(source)
    session.flush()
    stats.records_inserted += 1
    return source, status


def persist_affidavit(
    session: Session,
    normalized: NormalizedAffidavit,
    artifact: ArchivedArtifact,
    stats: RunStats,
    *,
    extraction_status: str,
    extraction_method: str,
) -> ParseOutcome:
    try:
        person, election, candidacy = resolve_person_and_election(session, normalized)
    except LinkageError as exc:
        if exc.code == "IDENTITY_REVIEW_REQUIRED":
            source, _ = get_or_create_source(
                session, artifact, stats, extraction_method=extraction_method
            )
            add_review(
                session,
                ReviewItemDraft(
                    review_type="IDENTITY_REVIEW_REQUIRED",
                    field="candidate_name",
                    reason=str(exc),
                    raw_text=normalized.candidate_name_raw,
                ),
                source_id=source.source_id,
                artifact=artifact,
            )
            stats.records_rejected += 1
            return ParseOutcome.IDENTITY_REVIEW_REQUIRED
        raise

    source, source_status = get_or_create_source(
        session, artifact, stats, extraction_method=extraction_method
    )
    if source_status == "SOURCE_CHANGED":
        add_review(
            session,
            ReviewItemDraft(
                review_type="DOCUMENT_REVIEW_REQUIRED",
                field="content_sha256",
                reason="SOURCE_CHANGED: bytes differ for same source URL",
                raw_text=artifact.sha256,
            ),
            source_id=source.source_id,
            artifact=artifact,
        )

    existing = session.scalars(
        select(Affidavit).where(
            Affidavit.person_id == person.person_id,
            Affidavit.document_sha256 == artifact.sha256,
        )
    ).first()
    if existing is not None:
        stats.records_unchanged += 1
        return ParseOutcome.UNCHANGED

    affidavit = Affidavit(
        affidavit_id=allocate_id(IdPrefix.AFFIDAVIT, _next_seq(session, Affidavit, "affidavit_id")),
        person_id=person.person_id,
        election_id=election.election_id,
        candidacy_id=candidacy.candidacy_id,
        original_document_url=artifact.source_url,
        local_archive_path=str(artifact.archive_dir),
        document_sha256=artifact.sha256,
        retrieved_at=artifact.retrieved_at,
        source_authority="Election Commission of India",
        source_id=source.source_id,
        extraction_status=extraction_status,
        parse_status=normalized.parse_outcome.value,
        parser_version=PARSER_VERSION,
    )
    session.add(affidavit)
    session.flush()
    stats.records_inserted += 1

    for edu in normalized.education:
        session.add(
            EducationDeclaration(
                declaration_id=allocate_id(
                    IdPrefix.EDUCATION, _next_seq(session, EducationDeclaration, "declaration_id")
                ),
                affidavit_id=affidavit.affidavit_id,
                person_id=person.person_id,
                declared_education=edu.declared_value_raw,
                declared_value_raw=edu.declared_value_raw,
                normalized_level=edu.normalized_level.value,
                institution_raw=edu.institution_raw,
                year_raw=edu.year_raw,
                field_status=edu.field_status.value,
                source_id=source.source_id,
            )
        )
        stats.records_inserted += 1

    for prof in normalized.profession:
        session.add(
            ProfessionDeclaration(
                declaration_id=allocate_id(
                    IdPrefix.PROFESSION, _next_seq(session, ProfessionDeclaration, "declaration_id")
                ),
                affidavit_id=affidavit.affidavit_id,
                person_id=person.person_id,
                declared_profession=prof.declared_value_raw,
                source_id=source.source_id,
            )
        )
        stats.records_inserted += 1

    for asset in normalized.assets:
        session.add(
            AssetDeclaration(
                declaration_id=allocate_id(
                    IdPrefix.ASSET, _next_seq(session, AssetDeclaration, "declaration_id")
                ),
                affidavit_id=affidavit.affidavit_id,
                person_id=person.person_id,
                asset_category=asset.asset_category,
                description=asset.description,
                declared_value_inr=asset.amount_value,
                amount_raw=asset.amount_raw,
                currency=asset.currency,
                field_status=asset.field_status.value,
                is_derived=asset.is_derived,
                source_id=source.source_id,
            )
        )
        stats.records_inserted += 1
        _maybe_queue_field_review(
            session,
            artifact,
            source_id=source.source_id,
            affidavit_id=affidavit.affidavit_id,
            field=f"assets.{asset.asset_category}",
            field_status=asset.field_status,
            raw_text=asset.amount_raw,
            page_number=asset.page_number,
        )

    for li in normalized.liabilities:
        session.add(
            LiabilityDeclaration(
                declaration_id=allocate_id(
                    IdPrefix.LIABILITY, _next_seq(session, LiabilityDeclaration, "declaration_id")
                ),
                affidavit_id=affidavit.affidavit_id,
                person_id=person.person_id,
                description=li.description,
                declared_value_inr=li.amount_value,
                amount_raw=li.amount_raw,
                currency=li.currency,
                field_status=li.field_status.value,
                is_derived=li.is_derived,
                source_id=source.source_id,
            )
        )
        stats.records_inserted += 1
        _maybe_queue_field_review(
            session,
            artifact,
            source_id=source.source_id,
            affidavit_id=affidavit.affidavit_id,
            field="liabilities.amount",
            field_status=li.field_status,
            raw_text=li.amount_raw,
            page_number=li.page_number,
        )

    for case in normalized.cases:
        session.add(
            CriminalCaseDeclaration(
                declaration_id=allocate_id(
                    IdPrefix.CASE, _next_seq(session, CriminalCaseDeclaration, "declaration_id")
                ),
                affidavit_id=affidavit.affidavit_id,
                person_id=person.person_id,
                case_summary=case.case_summary,
                disposition=case.normalized_status.value,
                case_number_raw=case.case_number_raw,
                court_raw=case.court_raw,
                act_raw=case.act_raw,
                section_raw=case.section_raw,
                status_raw=case.status_raw,
                date_raw=case.date_raw,
                field_status=case.field_status.value,
                ipc_sections=case.section_raw,
                source_id=source.source_id,
            )
        )
        stats.records_inserted += 1

    for inc in normalized.income:
        session.add(
            IncomeDeclaration(
                declaration_id=allocate_id(
                    IdPrefix.INCOME, _next_seq(session, IncomeDeclaration, "declaration_id")
                ),
                affidavit_id=affidavit.affidavit_id,
                person_id=person.person_id,
                description=inc.description,
                declared_value_inr=inc.amount_value,
                amount_raw=inc.amount_raw,
                currency=inc.currency,
                field_status=inc.field_status.value,
                assessment_year=inc.assessment_year,
                source_id=source.source_id,
            )
        )
        stats.records_inserted += 1
        _maybe_queue_field_review(
            session,
            artifact,
            source_id=source.source_id,
            affidavit_id=affidavit.affidavit_id,
            field="income.amount",
            field_status=inc.field_status,
            raw_text=inc.amount_raw,
            page_number=None,
        )

    if normalized.section_status.get("criminal_cases") == "NEEDS_REVIEW":
        add_review(
            session,
            ReviewItemDraft(
                review_type="FIELD_REVIEW_REQUIRED",
                field="criminal_cases",
                reason="Section marked NEEDS_REVIEW by fixture/parser",
                raw_text=None,
            ),
            source_id=source.source_id,
            artifact=artifact,
            affidavit_id=affidavit.affidavit_id,
        )

    session.flush()
    if source_status == "SOURCE_CHANGED":
        return ParseOutcome.SOURCE_CHANGED
    return normalized.parse_outcome


def _maybe_queue_field_review(
    session: Session,
    artifact: ArchivedArtifact,
    *,
    source_id: str,
    affidavit_id: str,
    field: str,
    field_status: FieldStatus,
    raw_text: str | None,
    page_number: int | None,
) -> None:
    if field_status not in _REVIEWABLE_FIELD_STATUSES:
        return
    add_review(
        session,
        ReviewItemDraft(
            review_type="FIELD_REVIEW_REQUIRED",
            field=field,
            reason=f"Financial field status {field_status.value}",
            raw_text=raw_text,
            page_number=page_number,
        ),
        source_id=source_id,
        artifact=artifact,
        affidavit_id=affidavit_id,
    )


def add_review(
    session: Session,
    draft: ReviewItemDraft,
    *,
    source_id: str,
    artifact: ArchivedArtifact,
    affidavit_id: str | None = None,
) -> ReviewItem:
    """Create an OPEN review item, or return the existing equivalent open item."""
    stmt = select(ReviewItem).where(
        ReviewItem.source_id == source_id,
        ReviewItem.review_type == draft.review_type,
        ReviewItem.status == "OPEN",
    )
    if draft.field is None:
        stmt = stmt.where(ReviewItem.field_name.is_(None))
    else:
        stmt = stmt.where(ReviewItem.field_name == draft.field)

    existing = session.scalars(stmt).first()
    if existing is not None:
        return existing

    rid = allocate_id(IdPrefix.REVIEW, _next_seq(session, ReviewItem, "review_id"))
    item = ReviewItem(
        review_id=rid,
        review_type=draft.review_type,
        field_name=draft.field,
        reason=draft.reason,
        raw_text=draft.raw_text,
        page_number=draft.page_number,
        source_id=source_id,
        affidavit_id=affidavit_id,
        archived_path=str(artifact.archive_dir),
        parser_version=PARSER_VERSION,
        status="OPEN",
    )
    session.add(item)
    session.flush()
    return item
