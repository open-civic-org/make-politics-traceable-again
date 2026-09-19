from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from collectors.base.artifacts import ArchivedArtifact, RawArtifact

# Dedup behavior: identical SHA-256 content is not rewritten. A new observation
# directory is created whose metadata points at the existing payload path.
# See docs/collectors.md.


class ArchiveError(Exception):
    """Raised when archive verification or write fails."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _atomic_write_bytes(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(target.parent), prefix=".tmp_", suffix=".partial")
    try:
        with os.fdopen(fd, "wb") as tmp:
            tmp.write(data)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_name, target)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _atomic_write_json(target: Path, payload: dict[str, Any]) -> None:
    data = (json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")
    _atomic_write_bytes(target, data)


def _find_existing_payload(raw_root: Path, source_name: str, sha256: str) -> Path | None:
    """Locate an existing payload with the same content hash under this source."""
    source_root = raw_root / source_name
    if not source_root.exists():
        return None
    for meta_path in source_root.rglob("metadata.json"):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if meta.get("sha256") != sha256:
            continue
        payload_rel = meta.get("payload_file")
        if not payload_rel:
            continue
        candidate = meta_path.parent / payload_rel
        if candidate.is_file() and sha256_file(candidate) == sha256:
            return candidate.resolve()
    return None


def archive_raw(
    artifact: RawArtifact,
    *,
    raw_root: Path,
    category: str = "generic",
    year: int | None = None,
    payload_filename: str = "payload.bin",
) -> ArchivedArtifact:
    """
    Persist raw bytes immutably under data/raw/{source}/{category}/{year}/{artifact_id}/.

    Never overwrites an existing artifact directory. Same SHA-256 content reuses the
    first payload bytes on disk; a new observation metadata directory is still created.
    """
    if not artifact.sha256:
        raise ArchiveError("artifact.sha256 is required")
    if artifact.sha256 != sha256_bytes(artifact.payload_bytes):
        raise ArchiveError("artifact.sha256 does not match payload_bytes")

    y = year or artifact.retrieved_at.year
    artifact_id = artifact.sha256[:16]
    archive_dir = raw_root / artifact.source_name / category / str(y) / artifact_id

    # Collision on same id+path: if directory exists with matching hash, return as-is;
    # if exists with different content, use a unique observation suffix.
    if archive_dir.exists():
        existing_meta = archive_dir / "metadata.json"
        if existing_meta.is_file():
            meta = json.loads(existing_meta.read_text(encoding="utf-8"))
            if meta.get("sha256") == artifact.sha256:
                payload_path = archive_dir / meta.get("payload_file", payload_filename)
                return ArchivedArtifact(
                    artifact_id=artifact_id,
                    source_name=artifact.source_name,
                    source_url=artifact.source_url,
                    retrieved_at=artifact.retrieved_at,
                    http_status=artifact.http_status,
                    content_type=artifact.content_type,
                    content_length=artifact.content_length,
                    sha256=artifact.sha256,
                    collector_version=artifact.collector_version,
                    git_commit_sha=artifact.git_commit_sha,
                    archive_dir=archive_dir,
                    payload_path=payload_path,
                    metadata_path=existing_meta,
                    deduplicated=True,
                    reused_payload_from=str(payload_path),
                    metadata=meta,
                )
        # Different content claimed same prefix — isolate observation
        stamp = artifact.retrieved_at.strftime("%Y%m%dT%H%M%S%f")
        artifact_id = f"{artifact.sha256[:12]}-{stamp}"
        archive_dir = raw_root / artifact.source_name / category / str(y) / artifact_id

    if archive_dir.exists():
        raise ArchiveError(f"refusing to overwrite existing archive: {archive_dir}")

    archive_dir.mkdir(parents=True, exist_ok=False)

    existing_payload = _find_existing_payload(raw_root, artifact.source_name, artifact.sha256)
    deduplicated = False
    reused_from: str | None = None

    if existing_payload is not None:
        # New observation: metadata only; payload path points at existing bytes.
        payload_path = existing_payload
        deduplicated = True
        reused_from = str(existing_payload)
        payload_file_meta: str = str(existing_payload)
        # Symlink local name for discoverability (optional); keep metadata absolute/relative
        link_name = archive_dir / payload_filename
        try:
            link_name.symlink_to(existing_payload)
            payload_file_meta = payload_filename
            payload_path = link_name
        except OSError:
            payload_file_meta = str(existing_payload)
            payload_path = existing_payload
    else:
        payload_path = archive_dir / payload_filename
        _atomic_write_bytes(payload_path, artifact.payload_bytes)
        payload_file_meta = payload_filename

    meta: dict[str, Any] = {
        "artifact_id": artifact_id,
        "source_name": artifact.source_name,
        "source_url": artifact.source_url,
        "retrieved_at": artifact.retrieved_at.isoformat(),
        "http_status": artifact.http_status,
        "content_type": artifact.content_type,
        "content_length": artifact.content_length
        if artifact.content_length is not None
        else len(artifact.payload_bytes),
        "sha256": artifact.sha256,
        "collector_version": artifact.collector_version,
        "git_commit_sha": artifact.git_commit_sha,
        "payload_file": payload_file_meta,
        "deduplicated": deduplicated,
        "reused_payload_from": reused_from,
        "category": category,
        "year": y,
        **artifact.metadata,
    }
    metadata_path = archive_dir / "metadata.json"
    _atomic_write_json(metadata_path, meta)

    return ArchivedArtifact(
        artifact_id=artifact_id,
        source_name=artifact.source_name,
        source_url=artifact.source_url,
        retrieved_at=artifact.retrieved_at,
        http_status=artifact.http_status,
        content_type=artifact.content_type,
        content_length=meta["content_length"],
        sha256=artifact.sha256,
        collector_version=artifact.collector_version,
        git_commit_sha=artifact.git_commit_sha,
        archive_dir=archive_dir,
        payload_path=payload_path,
        metadata_path=metadata_path,
        deduplicated=deduplicated,
        reused_payload_from=reused_from,
        metadata=meta,
    )


def verify_artifact(archive_dir: Path) -> dict[str, Any]:
    """
    Recalculate SHA-256 and ensure metadata/payload integrity.
    Raises ArchiveError on any mismatch.
    """
    meta_path = archive_dir / "metadata.json"
    if not meta_path.is_file():
        raise ArchiveError(f"missing metadata.json in {archive_dir}")

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ArchiveError(f"invalid metadata.json: {exc}") from exc

    expected = meta.get("sha256")
    if not expected or not isinstance(expected, str) or len(expected) != 64:
        raise ArchiveError("metadata missing valid sha256")

    payload_file = meta.get("payload_file")
    if not payload_file:
        raise ArchiveError("metadata missing payload_file")

    payload_path = Path(payload_file)
    if not payload_path.is_absolute():
        payload_path = archive_dir / payload_file

    if not payload_path.is_file():
        raise ArchiveError(f"missing payload: {payload_path}")

    actual = sha256_file(payload_path)
    if actual != expected:
        raise ArchiveError(
            f"sha256 mismatch for {payload_path}: expected {expected}, got {actual}"
        )

    return {"ok": True, "sha256": actual, "payload_path": str(payload_path), "metadata": meta}


def build_raw_from_bytes(
    *,
    source_name: str,
    source_url: str,
    payload: bytes,
    collector_version: str,
    git_commit_sha: str,
    retrieved_at: datetime | None = None,
    http_status: int | None = 200,
    content_type: str | None = "application/json",
    metadata: dict[str, Any] | None = None,
) -> RawArtifact:
    from datetime import UTC

    data = payload
    return RawArtifact(
        source_name=source_name,
        source_url=source_url,
        retrieved_at=retrieved_at or datetime.now(UTC),
        http_status=http_status,
        content_type=content_type,
        content_length=len(data),
        sha256=sha256_bytes(data),
        collector_version=collector_version,
        git_commit_sha=git_commit_sha,
        payload_bytes=data,
        metadata=metadata or {},
    )
