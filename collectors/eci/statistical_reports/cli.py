#!/usr/bin/env python3
"""CLI for offline ECI Statistical Report 33 fixture import (no live network)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from collectors.base.git import get_git_commit_sha
from collectors.eci.statistical_reports.schemas import (
    COLLECTOR_NAME,
    COLLECTOR_VERSION,
    PARSER_VERSION,
)
from collectors.eci.statistical_reports.staging import import_fixture_path
from collectors.eci.statistical_reports.workbook import extract_workbook
from packages.shared.logging import configure_logging, get_logger

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FIXTURE = (
    ROOT / "tests/fixtures/eci/statistical_reports/report33/report33_schema_fixture.xls"
)
logger = get_logger(__name__)


def _cmd_import_fixture(args: argparse.Namespace) -> int:
    path: Path = args.path
    if not path.is_file():
        logger.error("fixture not found: %s", path)
        return 1

    data = path.read_bytes()
    extracted = extract_workbook(data)
    sheet_names = [s.name for s in extracted.sheets]
    selected = sheet_names[0] if sheet_names else None
    extra = {
        "artifact_sha256": None,
        "container_format": extracted.detected_format,
        "workbook_status": extracted.format_status.value,
        "sheet_names": sheet_names,
        "selected_sheet": selected,
    }

    if args.dry_run:
        from collectors.eci.statistical_reports.staging import import_workbook_bytes

        summary = import_workbook_bytes(
            session=None,  # type: ignore[arg-type]
            data=data,
            source_url=args.source_url or f"fixture://eci/statistical_reports/report33/{path.name}",
            raw_root=args.raw_root,
            dry_run=True,
            election_type=args.election_type,
            election_year=args.election_year,
            git_commit_sha=get_git_commit_sha(),
        )
        extra["artifact_sha256"] = summary.source_sha256
        payload = {
            "collector": COLLECTOR_NAME,
            "collector_version": COLLECTOR_VERSION,
            "parser_version": PARSER_VERSION,
            **extra,
            **summary.as_dict(),
        }
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
        return 0

    from packages.db.session import session_scope

    with session_scope() as session:
        summary = import_fixture_path(
            session,
            path,
            raw_root=args.raw_root,
            dry_run=False,
            source_url=args.source_url,
            election_type=args.election_type,
            election_year=args.election_year,
            git_commit_sha=get_git_commit_sha(),
        )
        extra["artifact_sha256"] = summary.source_sha256
        payload = {
            "collector": COLLECTOR_NAME,
            "collector_version": COLLECTOR_VERSION,
            "parser_version": PARSER_VERSION,
            **extra,
            **summary.as_dict(),
        }
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 0


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(
        description="ECI Statistical Report staging CLI (offline only; no network)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    imp = sub.add_parser("import-fixture", help="Import a Report 33 workbook fixture")
    imp.add_argument(
        "path",
        type=Path,
        nargs="?",
        default=DEFAULT_FIXTURE,
        help="Path to Report 33 .xls/.xlsx fixture",
    )
    imp.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and summarize without archiving or inserting staging rows",
    )
    imp.add_argument("--source-url", default=None)
    imp.add_argument("--raw-root", type=Path, default=ROOT / "data" / "raw")
    imp.add_argument("--election-year", type=int, default=2024)
    imp.add_argument("--election-type", default="LOK_SABHA")
    imp.set_defaults(func=_cmd_import_fixture)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
