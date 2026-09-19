from __future__ import annotations

from datetime import UTC, datetime

from collectors.base.artifacts import ArchivedArtifact
from collectors.base.collector import RunStats
from collectors.eci.schemas import NormalizedElection
from packages.db.models import (
    Candidacy,
    Election,
    ElectionResult,
    ParliamentaryConstituency,
    Party,
    Person,
    SourceDocument,
    State,
)
from packages.shared.ids import IdPrefix, allocate_id, normalize_name
from sqlalchemy import select
from sqlalchemy.orm import Session


def _next_seq(session: Session, model, id_attr: str) -> int:
    ids = session.scalars(select(getattr(model, id_attr))).all()
    max_n = 0
    for raw in ids:
        try:
            max_n = max(max_n, int(str(raw).rsplit("-", 1)[-1]))
        except ValueError:
            continue
    return max_n + 1


def _get_or_create_source(
    session: Session, artifact: ArchivedArtifact, stats: RunStats
) -> SourceDocument:
    existing = session.scalars(
        select(SourceDocument).where(SourceDocument.content_sha256 == artifact.sha256)
    ).first()
    if existing:
        stats.records_unchanged += 1
        return existing

    source_id = allocate_id(IdPrefix.SOURCE, _next_seq(session, SourceDocument, "source_id"))
    source = SourceDocument(
        source_id=source_id,
        source_authority="Election Commission of India",
        source_type="ELECTION_RESULT",
        source_url=artifact.source_url,
        document_title=f"ECI election result {artifact.artifact_id}",
        publication_date=None,
        retrieved_at=artifact.retrieved_at,
        content_sha256=artifact.sha256,
        archived_path=str(artifact.archive_dir),
        collector_name="eci_election_results",
        collector_version=artifact.collector_version,
        parser_version=artifact.collector_version,
        git_commit_sha=artifact.git_commit_sha,
        extraction_method="fixture_json",
        extraction_confidence="HIGH",
        verification_status="UNVERIFIED",
    )
    session.add(source)
    session.flush()
    stats.records_inserted += 1
    return source


def _get_or_create_state(
    session: Session, name_raw: str, code: str | None, source_id: str, stats: RunStats
) -> State:
    normalized = normalize_name(name_raw)
    existing = session.scalars(select(State)).all()
    for st in existing:
        if normalize_name(st.name) == normalized:
            stats.records_unchanged += 1
            return st
    state = State(
        state_id=allocate_id(IdPrefix.STATE, _next_seq(session, State, "state_id")),
        name=name_raw,
        code=code[:8] if code else None,
        source_id=source_id,
    )
    session.add(state)
    session.flush()
    stats.records_inserted += 1
    return state


def _get_or_create_pc(
    session: Session,
    *,
    state_id: str,
    name_raw: str,
    eci_code: str | None,
    source_id: str,
    stats: RunStats,
) -> ParliamentaryConstituency:
    if eci_code:
        found = session.scalars(
            select(ParliamentaryConstituency).where(ParliamentaryConstituency.eci_code == eci_code)
        ).first()
        if found:
            stats.records_unchanged += 1
            return found
    normalized = normalize_name(name_raw)
    for pc in session.scalars(
        select(ParliamentaryConstituency).where(ParliamentaryConstituency.state_id == state_id)
    ).all():
        if normalize_name(pc.name) == normalized:
            stats.records_unchanged += 1
            return pc
    pc = ParliamentaryConstituency(
        pc_id=allocate_id(IdPrefix.PC, _next_seq(session, ParliamentaryConstituency, "pc_id")),
        state_id=state_id,
        name=name_raw,
        eci_code=eci_code,
        source_id=source_id,
    )
    session.add(pc)
    session.flush()
    stats.records_inserted += 1
    return pc


def _get_or_create_party(
    session: Session,
    *,
    name_raw: str,
    abbreviation: str | None,
    source_id: str,
    stats: RunStats,
) -> Party:
    normalized = normalize_name(name_raw)
    for party in session.scalars(select(Party)).all():
        if normalize_name(party.name) == normalized:
            stats.records_unchanged += 1
            return party
    party = Party(
        party_id=allocate_id(IdPrefix.PARTY, _next_seq(session, Party, "party_id")),
        name=name_raw,
        abbreviation=abbreviation,
        official_name=name_raw,
        registration_status=None,
        source_id=source_id,
    )
    session.add(party)
    session.flush()
    stats.records_inserted += 1
    return party


def _resolve_person(session: Session, *, name_raw: str, stats: RunStats) -> Person:
    """
    Exact controlled match only: reuse person iff exactly one row shares normalized_name.
    No fuzzy matching. Future ECI rows enter identity_match_review when ambiguous.
    """
    normalized = normalize_name(name_raw)
    matches = session.scalars(select(Person).where(Person.normalized_name == normalized)).all()
    if len(matches) == 1:
        stats.records_unchanged += 1
        return matches[0]
    # Ambiguous or missing → always create new (do not merge on name alone when >1)
    person = Person(
        person_id=allocate_id(IdPrefix.PERSON, _next_seq(session, Person, "person_id")),
        canonical_name=name_raw,
        normalized_name=normalized,
        current_party_id=None,
        current_office=None,
        is_demo=False,
    )
    session.add(person)
    session.flush()
    stats.records_inserted += 1
    return person


def _get_or_create_election(
    session: Session,
    *,
    normalized: NormalizedElection,
    state_id: str,
    pc_id: str,
    source_id: str,
    stats: RunStats,
) -> Election:
    # Prefer source election id + constituency; else type/year/pc
    q = select(Election).where(
        Election.election_type == normalized.election_type,
        Election.year == normalized.election_year,
        Election.constituency_pc_id == pc_id,
    )
    existing = session.scalars(q).first()
    if existing:
        stats.records_unchanged += 1
        return existing
    election = Election(
        election_id=allocate_id(IdPrefix.ELECTION, _next_seq(session, Election, "election_id")),
        election_type=normalized.election_type,
        year=normalized.election_year,
        election_date=normalized.election_date,
        state_id=state_id,
        constituency_pc_id=pc_id,
        source_id=source_id,
    )
    session.add(election)
    session.flush()
    stats.records_inserted += 1
    return election


def persist_normalized_election(
    session: Session,
    normalized: NormalizedElection,
    artifact: ArchivedArtifact,
    stats: RunStats,
) -> None:
    source = _get_or_create_source(session, artifact, stats)
    state = _get_or_create_state(
        session,
        normalized.constituency.state_name_raw,
        normalized.constituency.state_code,
        source.source_id,
        stats,
    )
    pc = _get_or_create_pc(
        session,
        state_id=state.state_id,
        name_raw=normalized.constituency.name_raw,
        eci_code=normalized.constituency.source_identifier,
        source_id=source.source_id,
        stats=stats,
    )
    election = _get_or_create_election(
        session,
        normalized=normalized,
        state_id=state.state_id,
        pc_id=pc.pc_id,
        source_id=source.source_id,
        stats=stats,
    )

    for cand in normalized.candidates:
        party = _get_or_create_party(
            session,
            name_raw=cand.party_name_raw,
            abbreviation=cand.party_abbreviation,
            source_id=source.source_id,
            stats=stats,
        )
        person = _resolve_person(session, name_raw=cand.candidate_name_raw, stats=stats)

        existing_cnd = session.scalars(
            select(Candidacy).where(
                Candidacy.person_id == person.person_id,
                Candidacy.election_id == election.election_id,
            )
        ).first()
        if existing_cnd is None:
            candidacy = Candidacy(
                candidacy_id=allocate_id(
                    IdPrefix.CANDIDACY, _next_seq(session, Candidacy, "candidacy_id")
                ),
                person_id=person.person_id,
                election_id=election.election_id,
                party_id=party.party_id,
                candidate_name_as_published=cand.candidate_name_raw,
                nomination_status="ACCEPTED",
                source_id=source.source_id,
            )
            session.add(candidacy)
            session.flush()
            stats.records_inserted += 1
            result = ElectionResult(
                result_id=allocate_id(
                    IdPrefix.RESULT, _next_seq(session, ElectionResult, "result_id")
                ),
                candidacy_id=candidacy.candidacy_id,
                votes_received=cand.votes,
                vote_share=cand.vote_share,
                result=cand.result or "UNKNOWN",
                winning_margin=None,
                rank=cand.rank,
                source_id=source.source_id,
            )
            session.add(result)
            stats.records_inserted += 1
        else:
            # Idempotent: update votes/rank only if changed; never delete history
            res = existing_cnd.result
            if res is None:
                res = ElectionResult(
                    result_id=allocate_id(
                        IdPrefix.RESULT, _next_seq(session, ElectionResult, "result_id")
                    ),
                    candidacy_id=existing_cnd.candidacy_id,
                    votes_received=cand.votes,
                    vote_share=cand.vote_share,
                    result=cand.result or "UNKNOWN",
                    rank=cand.rank,
                    source_id=source.source_id,
                )
                session.add(res)
                stats.records_inserted += 1
            elif (
                res.votes_received != cand.votes
                or res.rank != cand.rank
                or res.result != (cand.result or "UNKNOWN")
                or res.vote_share != cand.vote_share
            ):
                res.votes_received = cand.votes
                res.rank = cand.rank
                res.result = cand.result or "UNKNOWN"
                res.vote_share = cand.vote_share
                res.source_id = source.source_id
                stats.records_updated += 1
            else:
                stats.records_unchanged += 1

    session.flush()


def start_collector_run(
    session: Session,
    *,
    collector_name: str,
    collector_version: str,
    source: str,
    git_commit_sha: str,
    git_dirty: bool | None,
) -> str:
    from packages.db.models import CollectorRun

    run_id = allocate_id(IdPrefix.COLLECTOR_RUN, _next_seq(session, CollectorRun, "run_id"))
    session.add(
        CollectorRun(
            run_id=run_id,
            collector_name=collector_name,
            collector_version=collector_version,
            started_at=datetime.now(UTC),
            status="RUNNING",
            source=source,
            git_commit_sha=git_commit_sha,
            git_dirty=git_dirty,
        )
    )
    session.flush()
    return run_id


def finish_collector_run(
    session: Session,
    run_id: str,
    *,
    status: str,
    stats: RunStats,
) -> None:
    from packages.db.models import CollectorRun

    run = session.get(CollectorRun, run_id)
    if run is None:
        return
    run.finished_at = datetime.now(UTC)
    run.status = status
    run.artifacts_seen = stats.artifacts_seen
    run.artifacts_archived = stats.artifacts_archived
    run.records_parsed = stats.records_parsed
    run.records_valid = stats.records_valid
    run.records_rejected = stats.records_rejected
    run.records_inserted = stats.records_inserted
    run.records_updated = stats.records_updated
    run.records_unchanged = stats.records_unchanged
    run.error_message = stats.error_message
    session.flush()
