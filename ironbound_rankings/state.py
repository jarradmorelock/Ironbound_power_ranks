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


def save_state(path: Path, result: RankingResult, post_key: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "version": 1,
        "league_id": result.league.league_id,
        "last_published_key": post_key,
        "last_published_at": result.generated_at,
        "rank_by_roster_id": {
            str(team.roster_id): team.rank for team in result.teams
        },
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
