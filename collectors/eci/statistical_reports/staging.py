"""Persist statistical report staging rows (no canonical mutation)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from collectors.base.archive import archive_raw, build_raw_from_bytes
from collectors.base.artifacts import ArchivedArtifact
from collectors.base.collector import RunStats
from collectors.base.git import get_git_commit_sha
from collectors.eci.persist import SourceProvenance
from collectors.eci.statistical_reports.identity import reconcile_report_identity
from collectors.eci.statistical_reports.report33_parser import parse_report33_workbook
from collectors.eci.statistical_reports.schemas import (
    COLLECTOR_NAME,
    COLLECTOR_VERSION,
    PARSER_VERSION,
    ParsedStatisticalReport,
    RowStatus,
)
from collectors.eci.statistical_reports.workbook import extract_workbook
from packages.db.models import EciElectionResultSourceRecord, ReviewItem, SourceDocument
from packages.shared.ids import IdPrefix, allocate_id
from sqlalchemy import func, select
from sqlalchemy.orm import Session

STAT_EXTRACTION_METHOD = "archived_workbook"
STAT_SOURCE_TYPE = "ECI_STATISTICAL_REPORT"


def _next_seq(session: Session, model: type, id_attr: str) -> int:
    ids = session.scalars(select(getattr(model, id_attr))).all()
    max_n = 0
    for raw in ids:
        try:
            max_n = max(max_n, int(str(raw).rsplit("-", 1)[-1]))
        except ValueError:
            continue
    return max_n + 1


def _get_or_create_source(
    session: Session,
    artifact: ArchivedArtifact,
    stats: RunStats,
    provenance: SourceProvenance,
    *,
    document_title: str,
) -> tuple[SourceDocument, str]:
    """Return (source, status) where status is INSERTED | UNCHANGED | SOURCE_CHANGED."""
    existing_same = session.scalars(
        select(SourceDocument).where(SourceDocument.content_sha256 == artifact.sha256)
    ).first()
    if existing_same:
        stats.records_unchanged += 1
        return existing_same, "UNCHANGED"

    prior = None
    if artifact.source_url:
        prior = session.scalars(
            select(SourceDocument).where(SourceDocument.source_url == artifact.source_url)
        ).first()
    status = "SOURCE_CHANGED" if prior else "INSERTED"

    source_id = allocate_id(IdPrefix.SOURCE, _next_seq(session, SourceDocument, "source_id"))
    source = SourceDocument(
        source_id=source_id,
        source_authority="Election Commission of India",
        source_type=STAT_SOURCE_TYPE,
        source_url=artifact.source_url,
        document_title=document_title,
        publication_date=None,
        retrieved_at=artifact.retrieved_at,
        content_sha256=artifact.sha256,
        archived_path=str(artifact.archive_dir),
        collector_name=provenance.collector_name,
        collector_version=provenance.collector_version,
        parser_version=provenance.parser_version,
        git_commit_sha=artifact.git_commit_sha,
        extraction_method=provenance.extraction_method,
        extraction_confidence=None,
        verification_status="UNVERIFIED",
    )
    session.add(source)
    session.flush()
    stats.records_inserted += 1
    return source, status


def _add_source_changed_review(
    session: Session,
    *,
    source: SourceDocument,
    artifact: ArchivedArtifact,
    parser_version: str,
) -> None:
    existing = session.scalars(
        select(ReviewItem).where(
            ReviewItem.source_id == source.source_id,
            ReviewItem.review_type == "DOCUMENT_REVIEW_REQUIRED",
            ReviewItem.field_name == "content_sha256",
            ReviewItem.status == "OPEN",
        )
    ).first()
    if existing is not None:
        return
    session.add(
        ReviewItem(
            review_id=allocate_id(IdPrefix.REVIEW, _next_seq(session, ReviewItem, "review_id")),
            review_type="DOCUMENT_REVIEW_REQUIRED",
            field_name="content_sha256",
            reason=(
                "SOURCE_CHANGED: bytes differ for same source URL; "
                "prior staging rows retained; new source archived"
            ),
            raw_text=artifact.sha256,
            source_id=source.source_id,
            archived_path=str(artifact.archive_dir),
            parser_version=parser_version,
            status="OPEN",
        )
    )
    session.flush()


def _row_to_record(
    *,
    row,
    source: SourceDocument,
    report: ParsedStatisticalReport,
    git_commit_sha: str | None,
    record_seq: int,
) -> EciElectionResultSourceRecord:
    record_id = allocate_id(IdPrefix.STAT_SRC_REC, record_seq)
    return EciElectionResultSourceRecord(
        record_id=record_id,
        source_id=source.source_id,
        source_sha256=source.content_sha256 or "",
        report_number=report.report_number,
        report_title=report.report_title,
        election_type=report.election_type,
        election_year=report.election_year,
        sheet_name=row.sheet_name,
        source_row_number=row.source_row_number,
        state_raw=row.state.raw or "",
        state_normalized=row.state.normalized or "",
        constituency_number_raw=row.constituency_number.raw,
        constituency_name_raw=row.constituency_name.raw or "",
        constituency_name_normalized=row.constituency_name.normalized or "",
        candidate_name_raw=row.candidate_name.raw or "",
        candidate_name_normalized=row.candidate_name.normalized or "",
        party_name_raw=row.party_name.raw or "",
        party_name_normalized=row.party_name.normalized or "",
        gender_raw=row.gender.raw,
        age_raw=row.age.raw,
        category_raw=row.category.raw,
        symbol_raw=row.symbol.raw,
        votes_raw=row.votes.raw,
        votes_value=row.votes_value,
        vote_share_raw=row.vote_share.raw,
        vote_share_value=row.vote_share_value,
        votes_general_raw=row.votes_general.raw,
        votes_general_value=row.votes_general_value,
        votes_postal_raw=row.votes_postal.raw,
        votes_postal_value=row.votes_postal_value,
        total_electors_raw=row.total_electors.raw,
        total_electors_value=row.total_electors_value,
        valid_votes_raw=row.valid_votes.raw,
        valid_votes_value=row.valid_votes_value,
        total_votes_polled_raw=row.total_votes_polled.raw,
        total_votes_polled_value=row.total_votes_polled_value,
        result_raw=row.result_raw,
        result_normalized=row.result_normalized or "UNKNOWN",
        rank=row.rank,
        source_candidate_id=row.source_candidate_id,
        identity_status=row.identity_status.value,
        identity_candidacy_id=row.identity_candidacy_id,
        identity_notes=row.identity_notes,
        row_status=row.row_status.value,
        rejection_reason=row.rejection_reason,
        raw_row_json=json.dumps(row.raw_row, sort_keys=True, default=str),
        parser_version=report.parser_version,
        collector_version=COLLECTOR_VERSION,
        git_commit_sha=git_commit_sha,
    )


def persist_staging_rows(
    session: Session,
    report: ParsedStatisticalReport,
    artifact: ArchivedArtifact,
    stats: RunStats,
    *,
    provenance: SourceProvenance | None = None,
) -> dict[str, Any]:
    """
    Insert staging records only. Never mutates Person / Candidacy / ElectionResult.

    Idempotent on (source_id, sheet_name, source_row_number).
    SOURCE_CHANGED (same URL, different SHA): new SourceDocument + ReviewItem;
    prior staging rows for the old source are retained.
    """
    prov = provenance or SourceProvenance(
        collector_name=COLLECTOR_NAME,
        collector_version=COLLECTOR_VERSION,
        parser_version=PARSER_VERSION,
        extraction_method=STAT_EXTRACTION_METHOD,
    )
    source, source_status = _get_or_create_source(
        session,
        artifact,
        stats,
        prov,
        document_title=f"ECI Statistical Report {report.report_number}: {report.report_title}",
    )

    if source_status == "SOURCE_CHANGED":
        _add_source_changed_review(
            session,
            source=source,
            artifact=artifact,
            parser_version=prov.parser_version,
        )

    # Reconcile identity against existing canonical rows (read-only).
    reconcile_report_identity(
        session,
        report.rows,
        election_year=report.election_year,
        election_type=report.election_type,
    )

    inserted = 0
    skipped = 0
    next_record_seq = _next_seq(session, EciElectionResultSourceRecord, "record_id")
    for row in report.rows:
        existing = session.scalars(
            select(EciElectionResultSourceRecord).where(
                EciElectionResultSourceRecord.source_id == source.source_id,
                EciElectionResultSourceRecord.sheet_name == row.sheet_name,
                EciElectionResultSourceRecord.source_row_number == row.source_row_number,
            )
        ).first()
        if existing is not None:
            skipped += 1
            stats.records_unchanged += 1
            continue
        session.add(
            _row_to_record(
                row=row,
                source=source,
                report=report,
                git_commit_sha=artifact.git_commit_sha,
                record_seq=next_record_seq,
            )
        )
        next_record_seq += 1
        inserted += 1
        stats.records_inserted += 1
        if row.row_status == RowStatus.VALID:
            stats.records_valid += 1
        elif row.row_status == RowStatus.REJECTED:
            stats.records_rejected += 1
        stats.records_parsed += 1

    session.flush()
    return {
        "source_id": source.source_id,
        "source_status": source_status,
        "source_sha256": source.content_sha256,
        "rows_inserted": inserted,
        "rows_skipped": skipped,
        "rows_total": len(report.rows),
        "schema_status": report.schema_status.value,
        "coverage_status": report.coverage.coverage_status.value if report.coverage else None,
        "parser_version": report.parser_version,
        "extraction_confidence": source.extraction_confidence,
    }


@dataclass
class ImportSummary:
    source_status: str
    source_id: str | None
    source_sha256: str | None
    rows_inserted: int
    rows_skipped: int
    rows_total: int
    schema_status: str
    coverage_status: str | None
    parser_version: str
    collector_version: str
    dry_run: bool
    identity_counts: dict[str, int]
    row_status_counts: dict[str, int]
    person_count: int | None = None
    candidacy_count: int | None = None
    election_result_count: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_status": self.source_status,
            "source_id": self.source_id,
            "source_sha256": self.source_sha256,
            "rows_inserted": self.rows_inserted,
            "rows_skipped": self.rows_skipped,
            "rows_total": self.rows_total,
            "schema_status": self.schema_status,
            "coverage_status": self.coverage_status,
            "parser_version": self.parser_version,
            "collector_version": self.collector_version,
            "dry_run": self.dry_run,
            "identity_counts": self.identity_counts,
            "row_status_counts": self.row_status_counts,
            "person_count": self.person_count,
            "candidacy_count": self.candidacy_count,
            "election_result_count": self.election_result_count,
        }


def import_workbook_bytes(
    session: Session | None,
    data: bytes,
    *,
    source_url: str,
    raw_root: Path,
    dry_run: bool = False,
    election_type: str = "LOK_SABHA",
    election_year: int = 2024,
    git_commit_sha: str | None = None,
) -> ImportSummary:
    """Archive + parse + optionally stage a Report 33 workbook."""
    from packages.db.models import Candidacy, ElectionResult, Person

    git_sha = git_commit_sha or get_git_commit_sha()
    extracted = extract_workbook(data)
    report = parse_report33_workbook(
        extracted, election_type=election_type, election_year=election_year
    )

    identity_counts: dict[str, int] = {}
    row_status_counts: dict[str, int] = {}
    for row in report.rows:
        identity_counts[row.identity_status.value] = (
            identity_counts.get(row.identity_status.value, 0) + 1
        )
        row_status_counts[row.row_status.value] = row_status_counts.get(row.row_status.value, 0) + 1

    if dry_run:
        # Parse-only: no archive, no DB writes, no identity DB lookups.
        import hashlib

        return ImportSummary(
            source_status="DRY_RUN",
            source_id=None,
            source_sha256=hashlib.sha256(data).hexdigest(),
            rows_inserted=0,
            rows_skipped=0,
            rows_total=len(report.rows),
            schema_status=report.schema_status.value,
            coverage_status=report.coverage.coverage_status.value if report.coverage else None,
            parser_version=report.parser_version,
            collector_version=COLLECTOR_VERSION,
            dry_run=True,
            identity_counts=identity_counts,
            row_status_counts=row_status_counts,
        )

    if session is None:
        raise ValueError("session is required when dry_run is False")

    raw = build_raw_from_bytes(
        payload=data,
        source_name="eci",
        source_url=source_url,
        collector_version=COLLECTOR_VERSION,
        git_commit_sha=git_sha,
        content_type="application/vnd.ms-excel",
        retrieved_at=datetime.now(UTC),
    )
    archived = archive_raw(
        raw,
        raw_root=raw_root,
        category="statistical_reports",
        year=election_year,
        payload_filename="report33.xls",
    )
    stats = RunStats()
    stats.artifacts_seen = 1
    stats.artifacts_archived = 1
    result = persist_staging_rows(
        session,
        report,
        archived,
        stats,
        provenance=SourceProvenance(
            collector_name=COLLECTOR_NAME,
            collector_version=COLLECTOR_VERSION,
            parser_version=PARSER_VERSION,
            extraction_method=STAT_EXTRACTION_METHOD,
        ),
    )

    identity_counts = {}
    row_status_counts = {}
    for row in report.rows:
        identity_counts[row.identity_status.value] = (
            identity_counts.get(row.identity_status.value, 0) + 1
        )
        row_status_counts[row.row_status.value] = row_status_counts.get(row.row_status.value, 0) + 1

    return ImportSummary(
        source_status=result["source_status"],
        source_id=result["source_id"],
        source_sha256=result["source_sha256"],
        rows_inserted=result["rows_inserted"],
        rows_skipped=result["rows_skipped"],
        rows_total=result["rows_total"],
        schema_status=result["schema_status"],
        coverage_status=result["coverage_status"],
        parser_version=result["parser_version"],
        collector_version=COLLECTOR_VERSION,
        dry_run=False,
        identity_counts=identity_counts,
        row_status_counts=row_status_counts,
        person_count=session.scalar(select(func.count()).select_from(Person)),
        candidacy_count=session.scalar(select(func.count()).select_from(Candidacy)),
        election_result_count=session.scalar(select(func.count()).select_from(ElectionResult)),
    )


def import_fixture_path(
    session: Session,
    path: Path,
    *,
    raw_root: Path,
    dry_run: bool = False,
    source_url: str | None = None,
    election_type: str = "LOK_SABHA",
    election_year: int = 2024,
    git_commit_sha: str | None = None,
) -> ImportSummary:
    data = path.read_bytes()
    url = source_url or f"fixture://eci/statistical_reports/report33/{path.name}"
    return import_workbook_bytes(
        session,
        data,
        source_url=url,
        raw_root=raw_root,
        dry_run=dry_run,
        election_type=election_type,
        election_year=election_year,
        git_commit_sha=git_commit_sha,
    )
