"""Fixture-mode ECI Form-26 affidavit collector."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from collectors.base.archive import build_raw_from_bytes
from collectors.base.artifacts import ArchivedArtifact, RawArtifact
from collectors.base.collector import Collector, CollectorContext
from collectors.base.failures import write_failure_artifact
from collectors.eci.affidavits.extract import extract_document
from collectors.eci.affidavits.normalize import normalize_affidavit
from collectors.eci.affidavits.parser import AffidavitParseError, parse_extracted_document
from collectors.eci.affidavits.persist import add_review, get_or_create_source, persist_affidavit
from collectors.eci.affidavits.schemas import (
    COLLECTOR_NAME,
    COLLECTOR_VERSION,
    ExtractedDocument,
    ExtractionStatus,
    NormalizedAffidavit,
    ParsedAffidavit,
    ParseOutcome,
    ReviewItemDraft,
)
from collectors.eci.affidavits.validation import AffidavitValidationError, validate_affidavit
from collectors.eci.persist import finish_collector_run, start_collector_run
from sqlalchemy.orm import Session


class EciAffidavitCollector(Collector):
    """
    Fixture-mode ECI candidate-affidavit pipeline.

    Live HTTP fetching / OCR platforms are intentionally not implemented.
    """

    source_name = "eci"
    collector_version = COLLECTOR_VERSION

    def __init__(
        self,
        context: CollectorContext,
        *,
        session: Session,
        fixture_path: Path,
        source_url: str | None = None,
    ) -> None:
        super().__init__(context)
        self.session = session
        self.fixture_path = fixture_path
        self.source_url = source_url or f"fixture://{fixture_path.as_posix()}"
        self._run_id: str | None = None
        self._extraction: ExtractedDocument | None = None
        self._last_outcome: ParseOutcome | None = None

    def fetch(self) -> RawArtifact:
        payload = self.fixture_path.read_bytes()
        return build_raw_from_bytes(
            source_name=self.source_name,
            source_url=self.source_url,
            payload=payload,
            collector_version=self.collector_version,
            git_commit_sha=self.context.git_commit_sha,
            retrieved_at=datetime.now(UTC),
            http_status=200,
            content_type=_content_type(self.fixture_path),
            metadata={
                "mode": "fixture",
                "fixture_path": str(self.fixture_path),
                "live_network": False,
                "collector": COLLECTOR_NAME,
            },
        )

    def archive_raw(self, artifact: RawArtifact, **kwargs):  # type: ignore[override]
        suffix = self.fixture_path.suffix or ".bin"
        return super().archive_raw(
            artifact,
            category="affidavits",
            year=kwargs.get("year") or artifact.retrieved_at.year,
            payload_filename=f"affidavit{suffix}",
        )

    def parse(self, artifact: ArchivedArtifact) -> ParsedAffidavit:
        self._extraction = extract_document(artifact.payload_path)
        if self._extraction.extraction_status != ExtractionStatus.TEXT_EXTRACTED:
            raise AffidavitParseError(
                f"{self._extraction.extraction_status.value}: "
                f"{'; '.join(self._extraction.warnings) or 'no machine-readable text'}"
            )
        parsed = parse_extracted_document(self._extraction)
        self.context.stats.records_parsed = 1
        return parsed

    def normalize(self, parsed: ParsedAffidavit) -> NormalizedAffidavit:
        return normalize_affidavit(parsed)

    def validate(self, normalized: NormalizedAffidavit) -> NormalizedAffidavit:
        try:
            validated = validate_affidavit(normalized)
            self.context.stats.records_valid = 1
            return validated
        except AffidavitValidationError:
            self.context.stats.records_rejected += 1
            raise

    def persist(self, normalized: NormalizedAffidavit, artifact: ArchivedArtifact) -> None:
        status = (
            self._extraction.extraction_status.value
            if self._extraction
            else ExtractionStatus.TEXT_EXTRACTED.value
        )
        outcome = persist_affidavit(
            self.session,
            normalized,
            artifact,
            self.context.stats,
            extraction_status=status,
        )
        self._last_outcome = outcome
        self.session.flush()

    def run(self):
        self._run_id = start_collector_run(
            self.session,
            collector_name=COLLECTOR_NAME,
            collector_version=self.collector_version,
            source=self.source_url,
            git_commit_sha=self.context.git_commit_sha,
            git_dirty=self.context.git_dirty,
        )
        self.session.commit()
        stage = "fetch"
        try:
            raw = self.fetch()
            stage = "archive"
            archived = self.archive_raw(raw)
            stage = "extract"
            self._extraction = extract_document(archived.payload_path)
            if self._extraction.extraction_status != ExtractionStatus.TEXT_EXTRACTED:
                self._handle_unreadable(archived)
                finish_collector_run(
                    self.session, self._run_id, status="SUCCESS", stats=self.context.stats
                )
                self.session.commit()
                return self.context.stats

            stage = "parse"
            parsed = parse_extracted_document(self._extraction)
            self.context.stats.records_parsed = 1
            stage = "normalize"
            normalized = self.normalize(parsed)
            stage = "validate"
            validated = self.validate(normalized)
            stage = "persist"
            self.persist(validated, archived)
            finish_collector_run(
                self.session, self._run_id, status="SUCCESS", stats=self.context.stats
            )
            self.session.commit()
            return self.context.stats
        except Exception as exc:
            self.context.stats.error_message = f"{stage}: {exc}"
            write_failure_artifact(
                failures_dir=self.context.failures_dir,
                collector=COLLECTOR_NAME,
                version=self.collector_version,
                stage=stage,
                error=exc,
                git_commit_sha=self.context.git_commit_sha,
            )
            self.session.rollback()
            finish_collector_run(
                self.session, self._run_id, status="FAILED", stats=self.context.stats
            )
            self.session.commit()
            raise

    def _handle_unreadable(self, artifact: ArchivedArtifact) -> None:
        """Archive provenance + review; never invent empty declarations."""
        assert self._extraction is not None
        source, _ = get_or_create_source(self.session, artifact, self.context.stats)
        self._last_outcome = (
            ParseOutcome.FAILED
            if self._extraction.extraction_status == ExtractionStatus.EXTRACTION_FAILED
            else ParseOutcome.FAILED
        )
        add_review(
            self.session,
            ReviewItemDraft(
                review_type="DOCUMENT_REVIEW_REQUIRED",
                field="document_text",
                reason=(
                    f"{self._extraction.extraction_status.value}: "
                    f"{'; '.join(self._extraction.warnings) or 'unreadable affidavit'}"
                ),
                raw_text=None,
            ),
            source_id=source.source_id,
            artifact=artifact,
        )
        self.context.stats.records_rejected += 1
        self.session.flush()


def _content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "application/pdf"
    if suffix in {".txt", ".afi"}:
        return "text/plain"
    if suffix == ".json":
        return "application/json"
    return "application/octet-stream"
