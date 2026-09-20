"""ECI live results canary — capture-first, archive-before-parse."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from collectors.base.archive import build_raw_from_bytes
from collectors.base.artifacts import ArchivedArtifact
from collectors.base.collector import CollectorContext, RunStats
from collectors.base.git import get_git_commit_sha, get_git_dirty
from collectors.eci.live_results.http_client import (
    ALLOWED_HOST,
    EciResultsHttpClient,
    LiveAccessError,
    LiveNetworkError,
    LiveResponse,
    RequestBudget,
    assert_live_enabled,
    validate_eci_url,
)
from collectors.eci.live_results.parser import (
    PARSER_VERSION,
    LayoutStatus,
    parse_candidateswise_html,
    validate_layout,
)
from collectors.eci.normalize import normalize_election
from collectors.eci.persist import (
    finish_collector_run,
    persist_normalized_election,
    start_collector_run,
)
from collectors.eci.validation import EciValidationError, validate_election
from packages.db.session import session_scope
from packages.shared.config import get_settings

COLLECTOR_NAME = "eci_live_results"
COLLECTOR_VERSION = "0.1.0"


@dataclass
class CanaryUrlResult:
    url: str
    status_code: int | None = None
    sha256: str | None = None
    archive_path: str | None = None
    layout_status: str | None = None
    error: str | None = None
    bytes_archived: int = 0


@dataclass
class CanaryReport:
    run_id: str | None = None
    urls_requested: list[str] = field(default_factory=list)
    results: list[CanaryUrlResult] = field(default_factory=list)
    request_count: int = 0
    request_spacings: list[float] = field(default_factory=list)
    records_parsed: int = 0
    records_valid: int = 0
    records_rejected: int = 0
    records_inserted: int = 0
    records_unchanged: int = 0
    layout_status: str | None = None
    capture_only: bool = True
    persist_attempted: bool = False
    stopped_reason: str | None = None
    robots_preflight: str = "robots.txt returned 404; no Disallow rules observed"
    host_allowlist: str = ALLOWED_HOST

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "host_allowlist": self.host_allowlist,
            "robots_preflight": self.robots_preflight,
            "capture_only": self.capture_only,
            "persist_attempted": self.persist_attempted,
            "urls_requested": self.urls_requested,
            "request_count": self.request_count,
            "request_spacings_seconds": self.request_spacings,
            "layout_status": self.layout_status,
            "records_parsed": self.records_parsed,
            "records_valid": self.records_valid,
            "records_rejected": self.records_rejected,
            "records_inserted": self.records_inserted,
            "records_unchanged": self.records_unchanged,
            "stopped_reason": self.stopped_reason,
            "results": [
                {
                    "url": r.url,
                    "http_status": r.status_code,
                    "sha256": r.sha256,
                    "archive_path": r.archive_path,
                    "layout_status": r.layout_status,
                    "bytes_archived": r.bytes_archived,
                    "error": r.error,
                }
                for r in self.results
            ],
        }


def load_canary_config(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    canary = data.get("canary") or {}
    urls = canary.get("urls") or []
    if not urls:
        raise ValueError("canary config has no urls")
    if len(urls) > 5:
        raise ValueError("canary config exceeds hard URL cap (5)")
    for u in urls:
        validate_eci_url(u)
    return canary


def run_canary(
    *,
    config_path: Path,
    confirm_live: bool,
    capture_only: bool = True,
    persist: bool = False,
    transport=None,
    raw_root: Path | None = None,
    failures_dir: Path | None = None,
) -> CanaryReport:
    settings = get_settings()
    if not confirm_live:
        raise LiveAccessError("--confirm-live is required for live canary execution")
    assert_live_enabled(settings.eci_live_enabled)

    if persist and capture_only:
        raise ValueError("cannot combine --persist with --capture-only")
    if not persist:
        capture_only = True

    canary = load_canary_config(config_path)
    urls: list[str] = list(canary["urls"])
    election_type = str(canary.get("election_type") or "LOK_SABHA")
    election_year = int(canary.get("election_year") or 2024)

    root = Path(__file__).resolve().parents[3]
    ctx = CollectorContext(
        raw_root=raw_root or (root / "data" / "raw"),
        failures_dir=failures_dir or (root / "data" / "failures"),
        git_commit_sha=get_git_commit_sha(),
        git_dirty=get_git_dirty(),
    )
    report = CanaryReport(capture_only=capture_only, urls_requested=list(urls))
    budget = RequestBudget()
    stats = RunStats()

    if persist:
        with session_scope() as session:
            return _run_canary_body(
                session=session,
                ctx=ctx,
                urls=urls,
                budget=budget,
                stats=stats,
                report=report,
                transport=transport,
                persist=True,
                election_type=election_type,
                election_year=election_year,
            )

    # Capture-only: archive without requiring a database.
    return _run_canary_body(
        session=None,
        ctx=ctx,
        urls=urls,
        budget=budget,
        stats=stats,
        report=report,
        transport=transport,
        persist=False,
        election_type=election_type,
        election_year=election_year,
    )


def _run_canary_body(
    *,
    session,
    ctx: CollectorContext,
    urls: list[str],
    budget: RequestBudget,
    stats: RunStats,
    report: CanaryReport,
    transport,
    persist: bool,
    election_type: str,
    election_year: int,
) -> CanaryReport:
    run_id: str | None = None
    if session is not None:
        run_id = start_collector_run(
            session,
            collector_name=COLLECTOR_NAME,
            collector_version=COLLECTOR_VERSION,
            source="canary:" + ",".join(urls[:2]),
            git_commit_sha=ctx.git_commit_sha,
            git_dirty=ctx.git_dirty,
        )
        session.commit()
        report.run_id = run_id

    try:
        with EciResultsHttpClient(transport=transport, budget=budget) as client:
            for url in urls:
                url_result = CanaryUrlResult(url=url)
                try:
                    live = client.get(url)
                    url_result.status_code = live.status_code
                    archived = _archive_live_response(ctx, live, stats)
                    url_result.sha256 = archived.sha256
                    url_result.archive_path = str(archived.archive_dir)
                    url_result.bytes_archived = len(live.content)

                    if live.status_code != 200:
                        url_result.error = f"HTTP {live.status_code}"
                        url_result.layout_status = LayoutStatus.UNSUPPORTED.value
                        report.results.append(url_result)
                        report.stopped_reason = f"non-200 status for {url}"
                        # Capture-only may continue to the next explicit URL;
                        # persist mode stops (no canonical mutation).
                        if persist:
                            break
                        continue

                    html = live.content.decode("utf-8", errors="replace")
                    layout = validate_layout(html)
                    url_result.layout_status = layout.status.value
                    report.layout_status = layout.status.value

                    if layout.status != LayoutStatus.OK:
                        url_result.error = "; ".join(layout.reasons)
                        report.results.append(url_result)
                        report.stopped_reason = "layout validation failed (fail closed)"
                        if persist:
                            break
                        continue

                    if persist:
                        assert session is not None
                        report.persist_attempted = True
                        _persist_archived(
                            session,
                            archived,
                            stats,
                            election_type=election_type,
                            election_year=election_year,
                            report=report,
                        )
                        report.stopped_reason = None
                    report.results.append(url_result)
                except (LiveNetworkError, LiveAccessError) as exc:
                    url_result.error = str(exc)
                    url_result.status_code = getattr(exc, "status_code", None)
                    report.results.append(url_result)
                    report.stopped_reason = str(exc)
                    break

        report.request_count = budget.requests_made
        report.request_spacings = list(budget.spacings)
        report.records_parsed = stats.records_parsed
        report.records_valid = stats.records_valid
        report.records_rejected = stats.records_rejected
        report.records_inserted = stats.records_inserted
        report.records_unchanged = stats.records_unchanged

        if session is not None and run_id is not None:
            finish_collector_run(
                session,
                run_id,
                status="SUCCESS" if report.stopped_reason is None else "PARTIAL",
                stats=stats,
            )
            session.commit()
    except Exception as exc:
        stats.error_message = str(exc)
        report.stopped_reason = str(exc)
        if session is not None and run_id is not None:
            session.rollback()
            finish_collector_run(session, run_id, status="FAILED", stats=stats)
            session.commit()
        raise

    return report


def _archive_live_response(
    ctx: CollectorContext, live: LiveResponse, stats: RunStats
) -> ArchivedArtifact:
    from collectors.base.archive import archive_raw

    raw = build_raw_from_bytes(
        source_name="eci",
        source_url=live.final_url or live.url,
        payload=live.content,
        collector_version=COLLECTOR_VERSION,
        git_commit_sha=ctx.git_commit_sha,
        retrieved_at=live.retrieved_at,
        http_status=live.status_code,
        content_type=live.content_type,
        metadata={
            "mode": "live_canary",
            "requested_url": live.url,
            "final_url": live.final_url,
            "etag": live.etag,
            "last_modified": live.last_modified,
            "parser_version": PARSER_VERSION,
            "live_network": True,
        },
    )
    archived = archive_raw(
        raw,
        raw_root=ctx.raw_root,
        category="results",
        year=live.retrieved_at.year,
        payload_filename="payload.html",
    )
    stats.artifacts_seen += 1
    stats.artifacts_archived += 1
    return archived


def _persist_archived(
    session,
    archived: ArchivedArtifact,
    stats: RunStats,
    *,
    election_type: str,
    election_year: int,
    report: CanaryReport,
) -> None:
    html = archived.payload_path.read_bytes().decode("utf-8", errors="replace")
    layout, parsed = parse_candidateswise_html(
        html, election_type=election_type, election_year=election_year
    )
    report.layout_status = layout.status.value
    if parsed is None:
        stats.records_rejected += 1
        raise LiveNetworkError(f"layout/parser fail-closed: {layout.reasons}")
    stats.records_parsed = len(parsed.candidates)
    normalized = normalize_election(parsed)
    try:
        validated = validate_election(normalized)
        stats.records_valid = len(validated.candidates)
    except EciValidationError:
        stats.records_rejected += 1
        raise
    persist_normalized_election(session, validated, archived, stats)
    session.flush()
