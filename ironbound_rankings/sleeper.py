"""Load league, roster, record, and pick ownership data from Sleeper."""

from __future__ import annotations

from typing import Any

from .http import DataSourceError, HttpClient
from .models import (
    DraftPick,
    LeagueConfig,
    LeagueMatchup,
    LeagueSnapshot,
    LeagueTeam,
)


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
    start_week = int(settings.get("start_week") or 1)
    playoff_week_start = int(settings.get("playoff_week_start") or 15)
    playoff_teams = int(settings.get("playoff_teams") or max(2, len(rosters) // 2))
    divisions = int(settings.get("divisions") or 1)
    playoff_round_type = int(settings.get("playoff_round_type") or 0)
    league_average_match = int(settings.get("league_average_match") or 0) == 1
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
                division=int(roster_settings.get("division") or 0),
            )
        )

    matchup_end_week = max(playoff_week_start - 1, week - 1)
    matchups = _fetch_matchups(
        client,
        league_id=config.league_id,
        start_week=start_week,
        end_week=matchup_end_week,
    )
    try:
        bracket = client.get_json(
            f"{SLEEPER_BASE}/league/{config.league_id}/winners_bracket"
        )
        playoff_bracket = bracket if isinstance(bracket, list) else []
    except DataSourceError:
        playoff_bracket = []

    return LeagueSnapshot(
        league_id=config.league_id,
        league_name=str(league.get("name") or config.brand),
        season=season,
        week=week,
        is_superflex=is_superflex,
        ppr=ppr,
        roster_positions=roster_positions,
        teams=teams,
        start_week=start_week,
        playoff_week_start=playoff_week_start,
        playoff_teams=playoff_teams,
        divisions=divisions,
        playoff_round_type=playoff_round_type,
        league_average_match=league_average_match,
        matchups=matchups,
        playoff_bracket=playoff_bracket,
    )


def _fetch_matchups(
    client: HttpClient,
    *,
    league_id: str,
    start_week: int,
    end_week: int,
) -> list[LeagueMatchup]:
    matchups: list[LeagueMatchup] = []
    for week in range(start_week, end_week + 1):
        rows = client.get_json(f"{SLEEPER_BASE}/league/{league_id}/matchups/{week}")
        if not isinstance(rows, list):
            continue
        grouped: dict[int, list[dict[str, Any]]] = {}
        for row in rows:
            if not isinstance(row, dict) or row.get("matchup_id") is None:
                continue
            grouped.setdefault(int(row["matchup_id"]), []).append(row)
        for matchup_id, pair in grouped.items():
            if len(pair) != 2:
                continue
            pair.sort(key=lambda item: int(item.get("roster_id") or 0))
            one, two = pair
            matchups.append(
                LeagueMatchup(
                    week=week,
                    matchup_id=matchup_id,
                    roster_one=int(one["roster_id"]),
                    roster_two=int(two["roster_id"]),
                    points_one=_matchup_points(one),
                    points_two=_matchup_points(two),
                )
            )
    return matchups


def _matchup_points(row: dict[str, Any]) -> float:
    custom = row.get("custom_points")
    try:
        return float(custom if custom is not None else row.get("points") or 0)
    except (TypeError, ValueError):
        return 0.0


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
