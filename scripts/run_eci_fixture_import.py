#!/usr/bin/env python3
"""Import the fixture ECI election result (no live network)."""

from __future__ import annotations

from pathlib import Path

from collectors.base.collector import CollectorContext
from collectors.base.git import get_git_commit_sha, get_git_dirty
from collectors.eci.collector import EciElectionResultsCollector
from packages.db.session import session_scope
from packages.shared.logging import configure_logging, get_logger

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/eci/election_results/ge2024_demo_nagar.json"
logger = get_logger(__name__)


def main() -> None:
    configure_logging()
    ctx = CollectorContext(
        raw_root=ROOT / "data" / "raw",
        failures_dir=ROOT / "data" / "failures",
        git_commit_sha=get_git_commit_sha(),
        git_dirty=get_git_dirty(),
    )
    with session_scope() as session:
        collector = EciElectionResultsCollector(ctx, session=session, fixture_path=FIXTURE)
        stats = collector.run()
        logger.info("ECI fixture import complete: %s", stats.as_dict())


if __name__ == "__main__":
    main()
