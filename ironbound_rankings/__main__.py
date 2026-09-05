"""Command-line entry point."""

from __future__ import annotations

import argparse

from .publisher import run


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish Ironbound power rankings")
    parser.add_argument("--league", choices=("all", "main", "free"), default="all")
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Post to Discord. Without this flag the run is a safe preview.",
    )
    parser.add_argument("--force", action="store_true", help="Allow a same-week repost")
    parser.add_argument(
        "--scheduled",
        action="store_true",
        help="Publish only when the current America/New_York time is Saturday noon",
    )
    args = parser.parse_args()
    return run(
        league_selection=args.league,
        publish=args.publish,
        force=args.force,
        scheduled=args.scheduled,
    )


if __name__ == "__main__":
    raise SystemExit(main())
