"""Load the checked-in two-league publishing configuration."""

from __future__ import annotations

import json
from pathlib import Path

from .models import LeagueConfig, Theme


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = ROOT / "leagues.json"


def load_leagues(path: Path = DEFAULT_CONFIG_PATH) -> dict[str, LeagueConfig]:
    data = json.loads(path.read_text(encoding="utf-8"))
    leagues: dict[str, LeagueConfig] = {}
    for key, raw in data.get("leagues", {}).items():
        quarterback_mode = str(raw.get("quarterback_mode") or "auto").lower()
        if quarterback_mode not in {"auto", "one_qb", "superflex"}:
            raise ValueError(
                f"Invalid quarterback_mode for {key}: {quarterback_mode}"
            )
        theme = Theme(**raw["theme"])
        leagues[key] = LeagueConfig(
            key=key,
            league_id=str(raw["league_id"]),
            brand=str(raw["brand"]),
            publication=str(raw["publication"]),
            quarterback_mode=quarterback_mode,
            webhook_env=str(raw["webhook_env"]),
            tags_env=str(raw["tags_env"]),
            theme=theme,
        )
    if not leagues:
        raise ValueError("leagues.json does not define any leagues")
    return leagues
