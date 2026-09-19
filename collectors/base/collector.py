from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from collectors.base.archive import archive_raw
from collectors.base.artifacts import ArchivedArtifact, RawArtifact
from collectors.base.failures import write_failure_artifact
from collectors.base.git import get_git_commit_sha, get_git_dirty


@dataclass
class RunStats:
    artifacts_seen: int = 0
    artifacts_archived: int = 0
    records_parsed: int = 0
    records_valid: int = 0
    records_rejected: int = 0
    records_inserted: int = 0
    records_updated: int = 0
    records_unchanged: int = 0
    error_message: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifacts_seen": self.artifacts_seen,
            "artifacts_archived": self.artifacts_archived,
            "records_parsed": self.records_parsed,
            "records_valid": self.records_valid,
            "records_rejected": self.records_rejected,
            "records_inserted": self.records_inserted,
            "records_updated": self.records_updated,
            "records_unchanged": self.records_unchanged,
            "error_message": self.error_message,
        }


@dataclass
class CollectorContext:
    raw_root: Path
    failures_dir: Path
    git_commit_sha: str = field(default_factory=get_git_commit_sha)
    git_dirty: bool | None = field(default_factory=get_git_dirty)
    stats: RunStats = field(default_factory=RunStats)
    run_id: str | None = None


class Collector(ABC):
    """Minimal reusable collector pipeline."""

    source_name: str
    collector_version: str

    def __init__(self, context: CollectorContext) -> None:
        self.context = context

    @abstractmethod
    def fetch(self) -> RawArtifact:
        """Obtain raw bytes (network or fixture)."""

    def archive_raw(self, artifact: RawArtifact, **kwargs: Any) -> ArchivedArtifact:
        archived = archive_raw(artifact, raw_root=self.context.raw_root, **kwargs)
        self.context.stats.artifacts_seen += 1
        if not archived.deduplicated or archived.archive_dir.exists():
            self.context.stats.artifacts_archived += 1
        return archived

    @abstractmethod
    def parse(self, artifact: ArchivedArtifact) -> Any: ...

    @abstractmethod
    def normalize(self, parsed: Any) -> Any: ...

    @abstractmethod
    def validate(self, normalized: Any) -> Any: ...

    @abstractmethod
    def persist(self, normalized: Any, artifact: ArchivedArtifact) -> None: ...

    def run(self) -> RunStats:
        stage = "fetch"
        try:
            raw = self.fetch()
            stage = "archive"
            archived = self.archive_raw(raw)
            stage = "parse"
            parsed = self.parse(archived)
            stage = "normalize"
            normalized = self.normalize(parsed)
            stage = "validate"
            validated = self.validate(normalized)
            stage = "persist"
            self.persist(validated, archived)
            return self.context.stats
        except Exception as exc:
            self.context.stats.error_message = f"{stage}: {exc}"
            write_failure_artifact(
                failures_dir=self.context.failures_dir,
                collector=self.source_name,
                version=self.collector_version,
                stage=stage,
                error=exc,
                git_commit_sha=self.context.git_commit_sha,
            )
            raise

    def started_at(self) -> datetime:
        return datetime.now(UTC)
