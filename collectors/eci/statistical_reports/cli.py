#!/usr/bin/env python3
"""CLI for ECI statistical-report capture (manual / workflow_dispatch only)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from collectors.base.git import get_git_commit_sha
from collectors.eci.statistical_reports.capture import capture_report
from collectors.eci.statistical_reports.http_client import CaptureAccessError, CaptureNetworkError
from packages.shared.config import get_settings
from packages.shared.logging import configure_logging, get_logger

ROOT = Path(__file__).resolve().parents[3]
logger = get_logger(__name__)


def _cmd_capture(args: argparse.Namespace) -> int:
    settings = get_settings()
    try:
        report = capture_report(
            url=args.url,
            report_number=args.report_number,
            report_title=args.report_title,
            election_year=args.election_year,
            election_type=args.election_type,
            confirm_live=args.confirm_live,
            live_enabled=settings.eci_stat_report_live_enabled,
            raw_root=args.raw_root,
            git_commit_sha=get_git_commit_sha(),
        )
    except (CaptureAccessError, CaptureNetworkError, ValueError) as exc:
        logger.error("capture refused/stopped: %s", exc)
        print(json.dumps({"outcome": "FAILED", "error": str(exc)}, indent=2))
        return 2

    print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    if report.outcome == "SUCCESS":
        return 0
    if report.outcome == "CAPTURE_REJECTED":
        return 3
    return 1


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(
        description="ECI statistical-report capture (opt-in live; capture-only)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    cap = sub.add_parser("capture", help="Download one official report URL and archive bytes")
    cap.add_argument("--url", required=True, help="Official HTTPS ECI report URL")
    cap.add_argument(
        "--report-number",
        required=True,
        type=int,
        help="Positive integer report id (1..9999)",
    )
    cap.add_argument("--report-title", required=True)
    cap.add_argument("--election-year", type=int, required=True)
    cap.add_argument("--election-type", default="LOK_SABHA")
    cap.add_argument(
        "--confirm-live",
        action="store_true",
        help="Required acknowledgement for live network access",
    )
    cap.add_argument(
        "--raw-root",
        type=Path,
        default=ROOT / "data" / "raw",
        help="Immutable raw archive root",
    )
    cap.set_defaults(func=_cmd_capture)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
