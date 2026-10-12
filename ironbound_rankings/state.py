"""Persistent per-league movement and duplicate-publication state."""

from __future__ import annotations

import json
from datetime import datetime, timezone
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

    previous_ranks = dict(data.get("rank_by_roster_id") or {})
    previous_at = data.get("last_ranking_published_at")
    _reject_stale(result.generated_at, previous_at)
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
    _archive_snapshot(path, result, publication, post_key, previous_ranks)
    temporary.replace(path)


def _reject_stale(generated_at: str, previous_at: str | None) -> None:
    """Never roll the rolling baseline backward after another publisher runs."""
    if not previous_at:
        return
    try:
        new = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        old = datetime.fromisoformat(str(previous_at).replace("Z", "+00:00"))
        if new.tzinfo is None or old.tzinfo is None:
            return
    except (ValueError, TypeError):
        # Legacy test/legacy-state labels did not contain parseable timestamps.
        return
    if new.astimezone(timezone.utc) < old.astimezone(timezone.utc):
        raise ValueError("Refusing stale ranking publication: older than the current saved baseline")


def _archive_snapshot(
    state_path: Path,
    result: RankingResult,
    publication: str,
    post_key: str,
    previous: dict[str, int],
) -> Path:
    """Persist immutable dated rankings for every successful Tuesday/Saturday run."""
    label = str(result.generated_at).replace("+00:00", "Z")
    try:
        date = datetime.fromisoformat(label.replace("Z", "+00:00"))
        if date.tzinfo is not None:
            label = date.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    except ValueError:
        pass
    label = "".join(char if char.isalnum() or char in "_-" else "-" for char in label)
    folder = state_path.parent / "history" / state_path.stem
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / f"{label}-{publication}.json"
    ranks = {str(team.roster_id): int(team.rank) for team in result.teams}
    teams = [
        {
            "roster_id": int(team.roster_id),
            "team": getattr(team, "team_name", None),
            "rank": int(team.rank),
            "previous_rank": previous.get(str(team.roster_id)),
            "movement": (previous[str(team.roster_id)] - int(team.rank)
                         if str(team.roster_id) in previous else None),
            "score": getattr(team, "score", None),
        }
        for team in result.teams
    ]
    payload = {
        "schema_version": 1,
        "publication": publication,
        "generated_at": result.generated_at,
        "league_id": str(result.league.league_id),
        "season": getattr(result.league, "season", None),
        "ranking_week": getattr(result.league, "week", None),
        "post_key": post_key,
        "previous_rank_by_roster_id": previous,
        "rank_by_roster_id": ranks,
        "teams": teams,
    }
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if destination.exists():
        if destination.read_text(encoding="utf-8") != serialized:
            raise ValueError(f"Ranking history collision: {destination.name}")
        return destination
    with destination.open("x", encoding="utf-8") as handle:
        handle.write(serialized)
    return destination
