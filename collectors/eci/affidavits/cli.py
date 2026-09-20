#!/usr/bin/env python3
"""CLI for fixture-mode ECI affidavit import (no live network)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from collectors.base.collector import CollectorContext
from collectors.base.git import get_git_commit_sha, get_git_dirty
from collectors.eci.affidavits.collector import EciAffidavitCollector
from collectors.eci.affidavits.schemas import COLLECTOR_NAME, PARSER_VERSION
from packages.db.session import session_scope
from packages.shared.logging import configure_logging, get_logger

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FIXTURE = ROOT / "tests/fixtures/eci/affidavits/asha_verma_form26.txt"
logger = get_logger(__name__)


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description="Import an ECI affidavit fixture offline")
    parser.add_argument(
        "--fixture",
        type=Path,
        default=DEFAULT_FIXTURE,
        help="Path to affidavit fixture (.txt / .pdf)",
    )
    parser.add_argument(
        "--source-url",
        default=None,
        help="Logical source URL/identifier (defaults to fixture://…)",
    )
    parser.add_argument(
        "--raw-root",
        type=Path,
        default=ROOT / "data" / "raw",
        help="Immutable raw archive root",
    )
    parser.add_argument(
        "--failures-dir",
        type=Path,
        default=ROOT / "data" / "failures",
        help="Failure artifact directory",
    )
    args = parser.parse_args(argv)

    if not args.fixture.is_file():
        logger.error("fixture not found: %s", args.fixture)
        return 1

    ctx = CollectorContext(
        raw_root=args.raw_root,
        failures_dir=args.failures_dir,
        git_commit_sha=get_git_commit_sha(),
        git_dirty=get_git_dirty(),
    )
    with session_scope() as session:
        collector = EciAffidavitCollector(
            ctx,
            session=session,
            fixture_path=args.fixture,
            source_url=args.source_url,
        )
        stats = collector.run()
        payload = {
            "collector": COLLECTOR_NAME,
            "collector_version": collector.collector_version,
            "parser_version": PARSER_VERSION,
            "outcome": collector._last_outcome.value if collector._last_outcome else None,
            "stats": stats.as_dict(),
        }
        logger.info("affidavit import complete: %s", json.dumps(payload))
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
