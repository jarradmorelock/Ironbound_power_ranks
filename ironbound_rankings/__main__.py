"""Command-line entry point."""

from __future__ import annotations

import argparse

from .publisher import run


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish Ironbound power rankings")
    parser.add_argument("--league", choices=("all", "main", "free"), default="all")
    delivery = parser.add_mutually_exclusive_group()
    delivery.add_argument(
        "--publish",
        action="store_true",
        help="Post to Discord. Without this flag the run is a safe preview.",
    )
    delivery.add_argument(
        "--email",
        action="store_true",
        help="Email the generated images without posting to Discord or changing state.",
    )
    parser.add_argument("--force", action="store_true", help="Allow a same-week repost")
    parser.add_argument(
        "--scheduled",
        action="store_true",
        help="Apply the DST-correct guard for scheduled Discord or email delivery",
    )
    parser.add_argument(
        "--scheduled-cron",
        help="Exact schedule expression supplied by GitHub Actions",
    )
    args = parser.parse_args()
    return run(
        league_selection=args.league,
        publish=args.publish,
        force=args.force,
        scheduled=args.scheduled,
        scheduled_cron=args.scheduled_cron,
        email=args.email,
    )


if __name__ == "__main__":
    raise SystemExit(main())
