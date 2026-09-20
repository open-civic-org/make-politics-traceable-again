"""Storage backends for captured statistical reports.

V1 persists via local immutable archive (+ GitHub Actions artifact upload).
The interface is intentionally backend-swappable for future R2/S3/GCS.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class StoredCapture:
    """Result of persisting a capture observation."""

    artifact_id: str
    archive_dir: Path
    payload_path: Path
    metadata_path: Path
    sha256: str
    source_status: str  # FIRST_OBSERVATION | UNCHANGED | SOURCE_CHANGED


class CaptureStorage(Protocol):
    """Persistence boundary for acquisition outputs (local today, object storage later)."""

    def store(
        self,
        *,
        payload: bytes,
        payload_filename: str,
        metadata: dict,
        logical_key: str,
    ) -> StoredCapture:
        """Persist exact bytes + metadata. Never overwrite prior observations."""
        ...
