"""Persistent per-league movement and duplicate-publication state."""

from __future__ import annotations

import json
from pathlib import Path

from .models import RankingResult


def load_state(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(
    path: Path,
    result: RankingResult,
    post_key: str,
    *,
    publication: str = "discord",
) -> None:
    if publication not in {"discord", "email"}:
        raise ValueError(f"Unknown publication history: {publication}")

    path.parent.mkdir(parents=True, exist_ok=True)
    data = load_state(path)

    # Migrate the original single-purpose duplicate key without losing the
    # most recent successful Discord publication.
    legacy_key = data.pop("last_published_key", None)
    legacy_at = data.pop("last_published_at", None)
    if legacy_key and not data.get("last_discord_published_key"):
        data["last_discord_published_key"] = legacy_key
    if legacy_at and not data.get("last_discord_published_at"):
        data["last_discord_published_at"] = legacy_at

    data.update(
        {
            "version": 2,
            "league_id": result.league.league_id,
            "last_ranking_published_at": result.generated_at,
            "rank_by_roster_id": {
                str(team.roster_id): team.rank for team in result.teams
            },
            f"last_{publication}_published_key": post_key,
            f"last_{publication}_published_at": result.generated_at,
        }
    )
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
