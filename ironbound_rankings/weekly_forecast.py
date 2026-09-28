"""Forward-looking weekly matchup and remaining-schedule models.

This module is intentionally separate from the season/playoff Monte Carlo in
``forecast.py``.  The Power Rankings repository owns both, but the models answer
different questions and have different inputs.
"""

from __future__ import annotations

import random
from statistics import mean
from typing import Any

from .models import LeagueSnapshot, PlayerIdentity, RankingResult


DEFAULT_WEEKLY_SIMULATIONS = 10_000

ELIGIBLE = {
    "QB": {"QB"},
    "RB": {"RB"},
    "WR": {"WR"},
    "TE": {"TE"},
    "FLEX": {"RB", "WR", "TE"},
    "SUPER_FLEX": {"QB", "RB", "WR", "TE"},
}

POSITION_CV = {
    "QB": 0.22,
    "RB": 0.35,
    "WR": 0.40,
    "TE": 0.42,
}


def attach_remaining_schedule_strength(result: RankingResult) -> None:
    """Attach remaining schedule difficulty using the current Power Board index.

    The Power Rankings engine owns this calculation because the difficulty
    measure is explicitly defined by the same current index shown on its board.
    Repeated opponents count repeatedly because each scheduled game is a real
    future exposure.
    """
    snapshot = result.league
    score_by_roster = {team.roster_id: float(team.score) for team in result.teams}
    name_by_roster = {team.roster_id: team.team_name for team in result.teams}
    team_ids = {team.roster_id for team in snapshot.teams}
    rows: list[dict[str, Any]] = []

    for roster_id in sorted(team_ids):
        opponent_rows: list[dict[str, Any]] = []
        for matchup in sorted(
            snapshot.matchups,
            key=lambda row: (row.week, row.matchup_id, row.roster_one, row.roster_two),
        ):
            if not (snapshot.week <= matchup.week < snapshot.playoff_week_start):
                continue
            if roster_id == matchup.roster_one:
                opponent_id = matchup.roster_two
            elif roster_id == matchup.roster_two:
                opponent_id = matchup.roster_one
            else:
                continue
            if opponent_id not in score_by_roster:
                continue
            opponent_rows.append(
                {
                    "week": matchup.week,
                    "roster_id": opponent_id,
                    "team": name_by_roster.get(opponent_id, f"Roster {opponent_id}"),
                    "power_index": round(score_by_roster[opponent_id], 1),
                }
            )

        average_index = (
            round(mean(row["power_index"] for row in opponent_rows), 1)
            if opponent_rows
            else None
        )
        rows.append(
            {
                "roster_id": roster_id,
                "team": name_by_roster.get(roster_id, f"Roster {roster_id}"),
                "remaining_opponents": [row["roster_id"] for row in opponent_rows],
                "opponents": opponent_rows,
                "average_opponent_index": average_index,
            }
        )

    ranked = sorted(
        (row for row in rows if row["average_opponent_index"] is not None),
        key=lambda row: (-float(row["average_opponent_index"]), int(row["roster_id"])),
    )
    total = len(ranked)
    for difficulty_rank, row in enumerate(ranked, start=1):
        row["difficulty_rank"] = difficulty_rank
        row["grade"] = _schedule_grade(difficulty_rank, total)
    for row in rows:
        if row.get("difficulty_rank") is None:
            row["difficulty_rank"] = None
            row["grade"] = None

    result.remaining_schedule_strength = sorted(
        rows,
        key=lambda row: (
            row.get("difficulty_rank") is None,
            row.get("difficulty_rank") or 999,
            int(row["roster_id"]),
        ),
    )


def projection_fantasy_points(
    projection: dict[str, Any], scoring_settings: dict[str, float]
) -> float:
    """Score a Sleeper projection using league scoring when components exist.

    Sleeper projection payloads are not guaranteed to use one stable wrapper in
    every environment.  We accept either a direct stat dictionary or a nested
    ``stats`` dictionary.  A provider-supplied ``pts`` value is used only as the
    fallback when component scoring cannot be reconstructed.
    """
    if not isinstance(projection, dict):
        return 0.0
    stats = projection.get("stats")
    if not isinstance(stats, dict):
        stats = projection

    reconstructed = 0.0
    matched = False
    for key, weight in (scoring_settings or {}).items():
        if key not in stats:
            continue
        try:
            stat_value = float(stats.get(key) or 0.0)
            scoring_value = float(weight or 0.0)
        except (TypeError, ValueError):
            continue
        reconstructed += stat_value * scoring_value
        matched = True
    if matched:
        return round(reconstructed, 3)

    for container in (projection, stats):
        for key in ("pts", "points", "fantasy_points"):
            try:
                value = float(container.get(key))
            except (TypeError, ValueError, AttributeError):
                continue
            return round(value, 3)
    return 0.0


def attach_weekly_matchup_forecast(
    result: RankingResult,
    players: dict[str, PlayerIdentity],
    projections: dict[str, dict[str, Any]],
    *,
    scoring_settings: dict[str, float] | None = None,
    simulations: int = DEFAULT_WEEKLY_SIMULATIONS,
    unavailable_player_ids: set[str] | None = None,
) -> None:
    """Attach a simulated line/total for the current week's optimal lineups.

    Each team's legal lineup is optimized exactly once from the pregame mean
    projections.  Those selected players stay fixed through every simulation,
    preventing the model from granting managers perfect hindsight.
    """
    result.weekly_matchup_forecast = []
    if simulations <= 0:
        return
    snapshot = result.league
    current = [row for row in snapshot.matchups if row.week == snapshot.week]
    if not current:
        result.weekly_matchup_forecast = []
        return

    team_by_id = {team.roster_id: team for team in snapshot.teams}
    slots = _starter_slots(snapshot)
    projected_values = {
        str(player_id): projection_fantasy_points(row, scoring_settings or {})
        for player_id, row in (projections or {}).items()
        if isinstance(row, dict)
    }

    unavailable = set(unavailable_player_ids or ())

    def eligible_ids(team):
        excluded = unavailable | set(team.reserve_player_ids) | set(team.taxi_player_ids)
        return [pid for pid in team.player_ids if pid not in excluded]

    rows: list[dict[str, Any]] = []
    for matchup in sorted(current, key=lambda row: (row.matchup_id, row.roster_one)):
        team_one = team_by_id.get(matchup.roster_one)
        team_two = team_by_id.get(matchup.roster_two)
        if team_one is None or team_two is None:
            continue
        lineup_one = optimal_projected_lineup(
            eligible_ids(team_one), slots, players, projected_values
        )
        lineup_two = optimal_projected_lineup(
            eligible_ids(team_two), slots, players, projected_values
        )
        if not lineup_one or not lineup_two:
            continue

        score_one = round(sum(projected_values[player_id] for player_id in lineup_one), 1)
        score_two = round(sum(projected_values[player_id] for player_id in lineup_two), 1)
        total = round(score_one + score_two, 1)
        projected_difference = round(score_one - score_two, 1)

        seed = (
            f"weekly:{snapshot.league_id}:{snapshot.season}:{snapshot.week}:"
            f"{matchup.matchup_id}:{simulations}"
        )
        rng = random.Random(seed)
        wins_one = 0.0
        simulated_totals: list[float] = []
        simulated_margins: list[float] = []
        for _ in range(simulations):
            sim_one = _simulate_lineup(lineup_one, players, projected_values, rng)
            sim_two = _simulate_lineup(lineup_two, players, projected_values, rng)
            simulated_totals.append(sim_one + sim_two)
            simulated_margins.append(sim_one - sim_two)
            if sim_one > sim_two:
                wins_one += 1.0
            elif sim_one == sim_two:
                wins_one += 0.5

        simulated_total = mean(simulated_totals) if simulated_totals else total
        simulated_margin = (
            mean(simulated_margins)
            if simulated_margins
            else projected_difference
        )
        favorite_id = matchup.roster_one if simulated_margin >= 0 else matchup.roster_two
        favorite_name = team_one.team_name if simulated_margin >= 0 else team_two.team_name
        rows.append(
            {
                "projection_fetched_at": result.generated_at,
                "projection_source": "Sleeper weekly projections scored with league settings",
                "availability_checked": unavailable_player_ids is not None,
                "uncertainty_note": "Experimental independent-player normal draws with positional heuristic volatility; no calibrated player/game correlations. Reserve, taxi, and known unavailable players excluded.",
                "week": snapshot.week,
                "matchup_id": matchup.matchup_id,
                "roster_one": matchup.roster_one,
                "team_one": team_one.team_name,
                "roster_two": matchup.roster_two,
                "team_two": team_two.team_name,
                "projected_score_one": score_one,
                "projected_score_two": score_two,
                "projected_total": total,
                "over_under": _nearest_half(simulated_total),
                "favorite_roster_id": favorite_id,
                "favorite_team": favorite_name,
                "projected_margin": projected_difference,
                "simulated_margin": round(simulated_margin, 1),
                "favorite_by": round(abs(simulated_margin), 1),
                "spread": _nearest_half(abs(simulated_margin)),
                "win_probability_one": round(wins_one / simulations * 100.0, 1),
                "simulations": simulations,
                "model": "Sleeper projected-optimal legal lineup Monte Carlo",
                "optimal_lineup_one": list(lineup_one),
                "optimal_lineup_two": list(lineup_two),
            }
        )

    result.weekly_matchup_forecast = rows
    result.weekly_matchup_simulations = simulations
    result.weekly_matchup_model = "Sleeper projected-optimal legal lineup Monte Carlo"


def optimal_projected_lineup(
    player_ids: list[str],
    slots: list[str],
    players: dict[str, PlayerIdentity],
    projected_values: dict[str, float],
) -> tuple[str, ...]:
    """Return player IDs in legal slot order for the best pregame projection."""
    candidates = [
        (str(player_id), players[str(player_id)].position, projected_values.get(str(player_id), 0.0))
        for player_id in sorted(set(map(str, player_ids)))
        if str(player_id) in players
        and players[str(player_id)].position in {"QB", "RB", "WR", "TE"}
        and projected_values.get(str(player_id), 0.0) > 0
    ]
    candidates.sort(key=lambda row: (-row[2], row[0]))
    # Dynamic programming over occupied slots, not subsets of a dynasty roster.
    # Each player is processed once and can fill at most one slot.
    states = {0: (0.0, ())}
    for player_id, position, value in candidates:
        updated = dict(states)
        for mask, (score, assignments) in states.items():
            for index, slot in enumerate(slots):
                if mask & (1 << index) or position not in ELIGIBLE[slot]:
                    continue
                new_mask = mask | (1 << index)
                proposal = (score + value, tuple(sorted(assignments + ((index, player_id),))))
                incumbent = updated.get(new_mask)
                if incumbent is None or proposal[0] > incumbent[0] or (
                    proposal[0] == incumbent[0] and proposal[1] < incumbent[1]
                ):
                    updated[new_mask] = proposal
        states = updated
    best = states.get((1 << len(slots)) - 1)
    return tuple(pid for _, pid in best[1]) if best else ()


def _starter_slots(snapshot: LeagueSnapshot) -> list[str]:
    return [
        "QB" if slot == "SUPER_FLEX" and not snapshot.is_superflex else slot
        for slot in snapshot.roster_positions
        if slot in ELIGIBLE
    ]


def _simulate_lineup(
    lineup: tuple[str, ...],
    players: dict[str, PlayerIdentity],
    projected_values: dict[str, float],
    rng: random.Random,
) -> float:
    total = 0.0
    for player_id in lineup:
        mean_points = max(0.0, projected_values.get(player_id, 0.0))
        position = players[player_id].position
        deviation = max(1.5, mean_points * POSITION_CV.get(position, 0.38))
        total += max(0.0, rng.gauss(mean_points, deviation))
    return total


def _schedule_grade(rank: int, total: int) -> str:
    if total <= 1:
        return "C"
    percentile = (rank - 1) / (total - 1)
    if percentile <= 0.0625:
        return "F"
    if percentile <= 0.1875:
        return "D-"
    if percentile <= 0.3125:
        return "D"
    if percentile <= 0.4375:
        return "D+"
    if percentile <= 0.5625:
        return "C"
    if percentile <= 0.6875:
        return "B-"
    if percentile <= 0.8125:
        return "B"
    if percentile <= 0.9375:
        return "A"
    return "A+"


def _nearest_half(value: float) -> float:
    return round(float(value) * 2.0) / 2.0
