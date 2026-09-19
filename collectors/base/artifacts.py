from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class RawArtifact(BaseModel):
    """In-memory representation of a fetched (or fixture-loaded) payload."""

    source_name: str
    source_url: str
    retrieved_at: datetime
    http_status: int | None = None
    content_type: str | None = None
    content_length: int | None = None
    sha256: str
    collector_version: str
    git_commit_sha: str
    payload_bytes: bytes = Field(repr=False)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}


class ArchivedArtifact(BaseModel):
    """On-disk immutable archive reference."""

    artifact_id: str
    source_name: str
    source_url: str
    retrieved_at: datetime
    http_status: int | None = None
    content_type: str | None = None
    content_length: int | None = None
    sha256: str
    collector_version: str
    git_commit_sha: str
    archive_dir: Path
    payload_path: Path
    metadata_path: Path
    deduplicated: bool = False
    reused_payload_from: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
