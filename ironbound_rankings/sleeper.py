"""Load league, roster, record, and pick ownership data from Sleeper."""

from __future__ import annotations

from typing import Any

from .http import DataSourceError, HttpClient
from .models import DraftPick, LeagueConfig, LeagueSnapshot, LeagueTeam


SLEEPER_BASE = "https://api.sleeper.app/v1"


def fetch_league_snapshot(client: HttpClient, config: LeagueConfig) -> LeagueSnapshot:
    league = client.get_json(f"{SLEEPER_BASE}/league/{config.league_id}")
    users = client.get_json(f"{SLEEPER_BASE}/league/{config.league_id}/users")
    rosters = client.get_json(f"{SLEEPER_BASE}/league/{config.league_id}/rosters")
    traded_picks = client.get_json(
        f"{SLEEPER_BASE}/league/{config.league_id}/traded_picks"
    )
    state = client.get_json(f"{SLEEPER_BASE}/state/nfl")
    if not isinstance(league, dict) or not isinstance(rosters, list):
        raise DataSourceError(f"Sleeper returned invalid league data for {config.key}")
    if len(rosters) < 2:
        raise DataSourceError(f"Sleeper returned too few rosters for {config.key}")

    season = int(league.get("season") or state.get("season") or 0)
    week = int(state.get("week") or league.get("settings", {}).get("leg") or 0)
    settings = league.get("settings") or {}
    draft_rounds = int(settings.get("draft_rounds") or 4)
    roster_positions = [str(pos) for pos in league.get("roster_positions") or []]
    detected_superflex = (
        "SUPER_FLEX" in roster_positions or roster_positions.count("QB") > 1
    )
    if config.quarterback_mode == "one_qb":
        is_superflex = False
    elif config.quarterback_mode == "superflex":
        is_superflex = True
    else:
        is_superflex = detected_superflex
    ppr = float((league.get("scoring_settings") or {}).get("rec") or 0)

    user_map = {
        str(user.get("user_id")): user
        for user in users
        if isinstance(user, dict) and user.get("user_id")
    }
    roster_ids = [int(roster["roster_id"]) for roster in rosters]
    pick_map = _future_pick_ownership(
        roster_ids=roster_ids,
        traded_picks=traded_picks if isinstance(traded_picks, list) else [],
        season=season,
        in_season=str(league.get("status") or "") in {"in_season", "post_season"},
        draft_rounds=draft_rounds,
    )

    teams: list[LeagueTeam] = []
    for roster in rosters:
        roster_id = int(roster["roster_id"])
        owner_id = str(roster.get("owner_id") or "")
        user = user_map.get(owner_id, {})
        user_metadata = user.get("metadata") or {}
        roster_metadata = roster.get("metadata") or {}
        owner_name = str(
            user.get("display_name") or user.get("username") or f"Roster {roster_id}"
        )
        team_name = str(
            roster_metadata.get("team_name")
            or user_metadata.get("team_name")
            or owner_name
        ).strip()
        roster_settings = roster.get("settings") or {}
        points = float(roster_settings.get("fpts") or 0)
        points += float(roster_settings.get("fpts_decimal") or 0) / 100
        teams.append(
            LeagueTeam(
                roster_id=roster_id,
                owner_id=owner_id,
                team_name=team_name,
                owner_name=owner_name,
                player_ids=[str(item) for item in roster.get("players") or []],
                picks=pick_map.get(roster_id, []),
                wins=int(roster_settings.get("wins") or 0),
                losses=int(roster_settings.get("losses") or 0),
                ties=int(roster_settings.get("ties") or 0),
                points_for=points,
            )
        )

    return LeagueSnapshot(
        league_id=config.league_id,
        league_name=str(league.get("name") or config.brand),
        season=season,
        week=week,
        is_superflex=is_superflex,
        ppr=ppr,
        roster_positions=roster_positions,
        teams=teams,
    )


def _future_pick_ownership(
    *,
    roster_ids: list[int],
    traded_picks: list[dict[str, Any]],
    season: int,
    in_season: bool,
    draft_rounds: int,
) -> dict[int, list[DraftPick]]:
    first_year = season + 1 if in_season else season
    years = range(first_year, first_year + 3)
    ownership: dict[tuple[int, int, int], int] = {}
    for year in years:
        for round_number in range(1, draft_rounds + 1):
            for original_roster_id in roster_ids:
                ownership[(year, round_number, original_roster_id)] = original_roster_id

    for pick in traded_picks:
        try:
            key = (
                int(pick["season"]),
                int(pick["round"]),
                int(pick["roster_id"]),
            )
            owner_id = int(pick.get("owner_id") or pick["roster_id"])
        except (KeyError, TypeError, ValueError):
            continue
        if key in ownership and owner_id in roster_ids:
            ownership[key] = owner_id

    result = {roster_id: [] for roster_id in roster_ids}
    for (year, round_number, original_roster_id), owner_id in ownership.items():
        result[owner_id].append(
            DraftPick(
                year=year,
                round=round_number,
                original_roster_id=original_roster_id,
            )
        )
    for picks in result.values():
        picks.sort(key=lambda item: (item.year, item.round, item.original_roster_id))
    return result
