"""Reusable collector framework: raw archive, provenance, and run pipeline."""

from collectors.base.archive import archive_raw, verify_artifact
from collectors.base.artifacts import ArchivedArtifact, RawArtifact
from collectors.base.collector import Collector, CollectorContext, RunStats
from collectors.base.failures import write_failure_artifact
from collectors.base.git import get_git_commit_sha, get_git_dirty

__all__ = [
    "ArchivedArtifact",
    "Collector",
    "CollectorContext",
    "RawArtifact",
    "RunStats",
    "archive_raw",
    "get_git_commit_sha",
    "get_git_dirty",
    "verify_artifact",
    "write_failure_artifact",
]
