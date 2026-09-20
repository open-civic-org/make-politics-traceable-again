"""CLI for the guarded ECI live results canary."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from collectors.eci.live_results.canary import run_canary
from collectors.eci.live_results.http_client import LiveAccessError, LiveNetworkError
from packages.shared.logging import configure_logging, get_logger

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = Path(__file__).resolve().parent / "canary_urls.yaml"
logger = get_logger(__name__)


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description="ECI live results canary (opt-in only)")
    sub = parser.add_subparsers(dest="command", required=True)

    canary = sub.add_parser("canary", help="Run the tiny historical results canary")
    canary.add_argument("--confirm-live", action="store_true", help="Required acknowledgement")
    canary.add_argument(
        "--capture-only",
        action="store_true",
        default=False,
        help="Archive + layout-validate only (default if --persist not set)",
    )
    canary.add_argument(
        "--persist",
        action="store_true",
        help="Persist only after layout validation succeeds",
    )
    canary.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="YAML canary URL config",
    )

    args = parser.parse_args(argv)
    if args.command != "canary":
        parser.error("unknown command")

    capture_only = True
    persist = False
    if args.persist:
        capture_only = False
        persist = True
    elif args.capture_only:
        capture_only = True

    try:
        report = run_canary(
            config_path=args.config,
            confirm_live=args.confirm_live,
            capture_only=capture_only,
            persist=persist,
        )
    except (LiveAccessError, LiveNetworkError, ValueError) as exc:
        logger.error("canary refused/stopped: %s", exc)
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2

    print(json.dumps(report.as_dict(), indent=2))
    return 0 if report.stopped_reason is None else 1


if __name__ == "__main__":
    sys.exit(main())
