from __future__ import annotations

import json
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def write_failure_artifact(
    *,
    failures_dir: Path,
    collector: str,
    version: str,
    stage: str,
    error: BaseException,
    source_identifier: str | None = None,
    git_commit_sha: str = "UNKNOWN",
    extra: dict[str, Any] | None = None,
) -> Path:
    """Persist COLLECTOR_FAILURE.json (no secrets)."""
    failures_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    path = failures_dir / f"COLLECTOR_FAILURE_{stamp}.json"
    payload = {
        "collector": collector,
        "version": version,
        "time": datetime.now(UTC).isoformat(),
        "stage": stage,
        "exception_type": type(error).__name__,
        "message": str(error),
        "traceback": traceback.format_exc(limit=20),
        "source_identifier": source_identifier,
        "git_commit": git_commit_sha,
        **(extra or {}),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
