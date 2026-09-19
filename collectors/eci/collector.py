from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from collectors.base.archive import build_raw_from_bytes
from collectors.base.artifacts import ArchivedArtifact, RawArtifact
from collectors.base.collector import Collector, CollectorContext
from collectors.eci.normalize import normalize_election
from collectors.eci.parser import load_fixture_bytes, parse_archived_payload
from collectors.eci.persist import (
    finish_collector_run,
    persist_normalized_election,
    start_collector_run,
)
from collectors.eci.schemas import NormalizedElection, ParsedElection
from collectors.eci.validation import EciValidationError, validate_election
from sqlalchemy.orm import Session

COLLECTOR_VERSION = "0.1.0"
SOURCE_NAME = "eci"


class EciElectionResultsCollector(Collector):
    """
    Fixture-mode ECI election results collector.

    Live HTTP fetching is intentionally not implemented in this milestone.
    """

    source_name = SOURCE_NAME
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

    def fetch(self) -> RawArtifact:
        payload = load_fixture_bytes(self.fixture_path)
        import json

        election_year = None
        try:
            election_year = json.loads(payload.decode("utf-8"))["election"]["year"]
        except (KeyError, ValueError, json.JSONDecodeError):
            pass
        return build_raw_from_bytes(
            source_name=self.source_name,
            source_url=self.source_url,
            payload=payload,
            collector_version=self.collector_version,
            git_commit_sha=self.context.git_commit_sha,
            retrieved_at=datetime.now(UTC),
            http_status=200,
            content_type="application/json",
            metadata={
                "mode": "fixture",
                "fixture_path": str(self.fixture_path),
                "live_network": False,
                "election_year": election_year,
            },
        )

    def archive_raw(self, artifact: RawArtifact, **kwargs):  # type: ignore[override]
        year = kwargs.get("year") or artifact.metadata.get("election_year")
        return super().archive_raw(
            artifact,
            category="election_results",
            year=int(year) if year is not None else None,
            payload_filename="payload.json",
        )

    def parse(self, artifact: ArchivedArtifact) -> ParsedElection:
        parsed = parse_archived_payload(artifact)
        self.context.stats.records_parsed = len(parsed.candidates)
        return parsed

    def normalize(self, parsed: ParsedElection) -> NormalizedElection:
        return normalize_election(parsed)

    def validate(self, normalized: NormalizedElection) -> NormalizedElection:
        try:
            validated = validate_election(normalized)
            self.context.stats.records_valid = len(validated.candidates)
            return validated
        except EciValidationError:
            self.context.stats.records_rejected += 1
            raise

    def persist(self, normalized: NormalizedElection, artifact: ArchivedArtifact) -> None:
        persist_normalized_election(self.session, normalized, artifact, self.context.stats)
        self.session.flush()

    def run(self):
        self._run_id = start_collector_run(
            self.session,
            collector_name="eci_election_results",
            collector_version=self.collector_version,
            source=self.source_url,
            git_commit_sha=self.context.git_commit_sha,
            git_dirty=self.context.git_dirty,
        )
        self.session.commit()
        try:
            stats = super().run()
            finish_collector_run(self.session, self._run_id, status="SUCCESS", stats=stats)
            self.session.commit()
            return stats
        except Exception as exc:
            self.context.stats.error_message = str(exc)
            self.session.rollback()
            finish_collector_run(
                self.session, self._run_id, status="FAILED", stats=self.context.stats
            )
            self.session.commit()
            raise
