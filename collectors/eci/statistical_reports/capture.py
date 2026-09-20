"""Capture orchestration: guarded download → exact-byte archive → provenance report.

Does NOT parse workbooks into staging/canonical rows.
Does NOT create Person / Candidacy / ElectionResult.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from collectors.base.archive import archive_raw, build_raw_from_bytes
from collectors.base.git import get_git_commit_sha
from collectors.eci.statistical_reports.format_detect import detect_container_format
from collectors.eci.statistical_reports.http_client import (
    ALLOWED_HOSTS,
    MAX_HTTP_ATTEMPTS,
    MAX_REPORT_BYTES,
    MAX_REPORTS_PER_RUN,
    CaptureAccessError,
    CaptureNetworkError,
    CaptureResponse,
    EciStatisticalReportHttpClient,
    RequestBudget,
    assert_live_enabled,
    validate_capture_url,
)
from collectors.eci.statistical_reports.storage import StoredCapture

COLLECTOR_NAME = "eci_statistical_report_capture"
COLLECTOR_VERSION = "ECI_STAT_REPORT_CAPTURE_V1"
SOURCE_AUTHORITY = "Election Commission of India"
SOURCE_TYPE = "ELECTION_STATISTICAL_REPORT"
CAPTURE_METHOD = "GITHUB_ACTION_WORKFLOW_DISPATCH"


@dataclass
class CaptureReport:
    outcome: str  # SUCCESS | CAPTURE_REJECTED | FAILED
    # FIRST_OBSERVATION = no prior state in this archive root (typical GHA runner).
    # UNCHANGED / SOURCE_CHANGED only when prior metadata exists under raw_root.
    source_status: str | None = None
    requested_url: str | None = None
    final_url: str | None = None
    http_status: int | None = None
    report_number: str | None = None
    report_title: str | None = None
    election_year: int | None = None
    election_type: str | None = None
    bytes_downloaded: int = 0
    sha256: str | None = None
    reported_content_type: str | None = None
    detected_container_format: str | None = None
    artifact_id: str | None = None
    archive_dir: str | None = None
    payload_path: str | None = None
    artifact_name: str | None = None
    requests_made: int = 0
    error: str | None = None
    allowed_hosts: list[str] = field(default_factory=lambda: sorted(ALLOWED_HOSTS))

    def as_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "source_status": self.source_status,
            "requested_url": self.requested_url,
            "final_url": self.final_url,
            "http_status": self.http_status,
            "report_number": self.report_number,
            "report_title": self.report_title,
            "election_year": self.election_year,
            "election_type": self.election_type,
            "bytes_downloaded": self.bytes_downloaded,
            "sha256": self.sha256,
            "reported_content_type": self.reported_content_type,
            "detected_container_format": self.detected_container_format,
            "artifact_id": self.artifact_id,
            "archive_dir": self.archive_dir,
            "payload_path": self.payload_path,
            "artifact_name": self.artifact_name,
            "requests_made": self.requests_made,
            "error": self.error,
            "allowed_hosts": self.allowed_hosts,
            "collector_name": COLLECTOR_NAME,
            "collector_version": COLLECTOR_VERSION,
            "max_report_bytes": MAX_REPORT_BYTES,
            "max_http_attempts": MAX_HTTP_ATTEMPTS,
            "max_reports_per_run": MAX_REPORTS_PER_RUN,
        }


def logical_source_key(
    *,
    election_type: str,
    election_year: int,
    report_number: str,
) -> str:
    return f"{SOURCE_AUTHORITY}|{election_type}|{election_year}|{report_number.strip()}"


def _find_prior_observation(
    raw_root: Path,
    *,
    election_year: int,
    report_number: str,
    election_type: str,
) -> dict[str, Any] | None:
    """Find most recent metadata for the same logical report (if any)."""
    base = raw_root / "eci" / "statistical_reports"
    if not base.exists():
        return None
    key = logical_source_key(
        election_type=election_type,
        election_year=election_year,
        report_number=report_number,
    )
    matches: list[tuple[str, dict[str, Any]]] = []
    for meta_path in base.rglob("metadata.json"):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if meta.get("logical_source_key") == key:
            matches.append((str(meta_path), meta))
    if not matches:
        return None
    matches.sort(key=lambda item: item[1].get("retrieved_at") or "", reverse=True)
    return matches[0][1]


def _extension_for_format(fmt: str | None) -> str:
    if fmt == "xlsx":
        return "xlsx"
    if fmt == "OLE_CFB":
        return "ole"
    return "bin"


def _artifact_name(
    *,
    election_type: str,
    election_year: int,
    report_number: str,
    sha256: str,
) -> str:
    et = re.sub(r"[^a-z0-9]+", "-", election_type.lower()).strip("-")
    return f"eci-{et}-{election_year}-report-{report_number}-{sha256[:12]}"


class LocalArchiveCaptureStorage:
    """V1 storage: write through collectors.base.archive.archive_raw."""

    def __init__(self, raw_root: Path) -> None:
        self.raw_root = raw_root

    def store(
        self,
        *,
        payload: bytes,
        payload_filename: str,
        metadata: dict[str, Any],
        logical_key: str,
    ) -> StoredCapture:
        sha = hashlib.sha256(payload).hexdigest()
        prior = _find_prior_observation(
            self.raw_root,
            election_year=int(metadata["election_year"]),
            report_number=str(metadata["report_number"]),
            election_type=str(metadata["election_type"]),
        )
        if prior and prior.get("sha256") == sha:
            source_status = "UNCHANGED"
        elif prior and prior.get("sha256") and prior.get("sha256") != sha:
            source_status = "SOURCE_CHANGED"
        else:
            # No durable prior under this raw_root (fresh GHA runners hit this path).
            source_status = "FIRST_OBSERVATION"

        meta = dict(metadata)
        meta["logical_source_key"] = logical_key
        meta["source_status"] = source_status
        if prior:
            meta["prior_sha256"] = prior.get("sha256")
            meta["prior_artifact_id"] = prior.get("artifact_id")

        raw = build_raw_from_bytes(
            source_name="eci",
            source_url=str(meta.get("final_url") or meta.get("requested_url")),
            payload=payload,
            collector_version=COLLECTOR_VERSION,
            git_commit_sha=str(meta.get("git_commit_sha") or "UNKNOWN"),
            retrieved_at=datetime.fromisoformat(str(meta["retrieved_at"]).replace("Z", "+00:00"))
            if isinstance(meta.get("retrieved_at"), str)
            else meta.get("retrieved_at"),
            http_status=meta.get("http_status"),
            content_type=meta.get("reported_content_type"),
            metadata=meta,
        )
        # Force sha consistency
        assert raw.sha256 == sha

        year = int(metadata["election_year"])
        report_number = str(metadata["report_number"])
        # archive_raw uses category/year; nest report under metadata + path convention
        archived = archive_raw(
            raw,
            raw_root=self.raw_root,
            category=f"statistical_reports/report_{report_number}",
            year=year,
            payload_filename=payload_filename,
        )
        return StoredCapture(
            artifact_id=archived.artifact_id,
            archive_dir=archived.archive_dir,
            payload_path=archived.payload_path,
            metadata_path=archived.archive_dir / "metadata.json",
            sha256=sha,
            source_status=source_status,
        )


def capture_report(
    *,
    url: str,
    report_number: str,
    report_title: str,
    election_year: int,
    election_type: str,
    confirm_live: bool,
    live_enabled: bool,
    raw_root: Path,
    transport=None,
    git_commit_sha: str | None = None,
) -> CaptureReport:
    """Download exactly one report URL and archive exact bytes."""
    report = CaptureReport(
        outcome="FAILED",
        report_number=report_number,
        report_title=report_title,
        election_year=election_year,
        election_type=election_type,
        requested_url=url,
    )

    if not confirm_live:
        report.error = "--confirm-live is required"
        report.outcome = "FAILED"
        return report

    try:
        assert_live_enabled(live_enabled)
        validate_capture_url(url)
    except CaptureAccessError as exc:
        report.error = str(exc)
        report.outcome = "FAILED"
        return report

    budget = RequestBudget()
    try:
        with EciStatisticalReportHttpClient(transport=transport, budget=budget) as client:
            # Enforce one report per run at the orchestration layer.
            if MAX_REPORTS_PER_RUN != 1:
                raise CaptureAccessError("MAX_REPORTS_PER_RUN must be 1")
            live: CaptureResponse = client.get(url)
    except (CaptureAccessError, CaptureNetworkError) as exc:
        report.error = str(exc)
        report.outcome = "FAILED"
        report.http_status = getattr(exc, "status_code", None)
        report.requests_made = budget.requests_made
        return report

    report.final_url = live.final_url
    report.http_status = live.status_code
    report.bytes_downloaded = len(live.content)
    report.reported_content_type = live.content_type
    report.requests_made = live.requests_made
    report.sha256 = hashlib.sha256(live.content).hexdigest()

    detected, reject_reason = detect_container_format(live.content)
    report.detected_container_format = detected
    if detected is None:
        report.outcome = "CAPTURE_REJECTED"
        report.error = reject_reason or "unsupported content"
        return report

    git_sha = git_commit_sha or get_git_commit_sha()
    payload_name = f"payload.{_extension_for_format(detected)}"
    metadata = {
        "source_authority": SOURCE_AUTHORITY,
        "source_type": SOURCE_TYPE,
        "requested_url": live.requested_url,
        "final_url": live.final_url,
        "report_number": report_number,
        "report_title": report_title,
        "election_type": election_type,
        "election_year": election_year,
        "retrieved_at": live.retrieved_at.isoformat(),
        "http_status": live.status_code,
        "content_type": live.content_type,
        "reported_content_type": live.content_type,
        "content_length": len(live.content),
        "content_length_header": live.content_length_header,
        "detected_container_format": detected,
        "sha256": report.sha256,
        "collector_name": COLLECTOR_NAME,
        "collector_version": COLLECTOR_VERSION,
        "git_commit_sha": git_sha,
        "capture_method": CAPTURE_METHOD,
        "etag": live.etag,
        "last_modified": live.last_modified,
        "content_disposition": live.content_disposition,
    }

    storage = LocalArchiveCaptureStorage(raw_root)
    stored = storage.store(
        payload=live.content,
        payload_filename=payload_name,
        metadata=metadata,
        logical_key=logical_source_key(
            election_type=election_type,
            election_year=election_year,
            report_number=report_number,
        ),
    )

    # Also write a capture_report.json alongside for workflow summaries.
    capture_report_path = stored.archive_dir / "capture_report.json"
    report.outcome = "SUCCESS"
    report.source_status = stored.source_status
    report.artifact_id = stored.artifact_id
    report.archive_dir = str(stored.archive_dir)
    report.payload_path = str(stored.payload_path)
    report.artifact_name = _artifact_name(
        election_type=election_type,
        election_year=election_year,
        report_number=report_number,
        sha256=stored.sha256,
    )
    capture_report_path.write_text(
        json.dumps(report.as_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report
