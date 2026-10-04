"""Projection-based rest-of-season lineup strength."""

from __future__ import annotations

from statistics import mean

from .http import DataSourceError, HttpClient
from .models import LeagueSnapshot, PlayerIdentity
from .sleeper import fetch_weekly_projections
from .weekly_forecast import optimal_projected_lineup, projection_fantasy_points


OFFENSE = {"QB", "RB", "WR", "TE"}


def ros_projection_weeks(snapshot: LeagueSnapshot) -> list[int]:
    """Return remaining fantasy weeks through the championship."""
    start = max(snapshot.start_week, snapshot.week or snapshot.start_week)
    end = max(start, min(17, snapshot.playoff_week_start + 2))
    return list(range(start, end + 1))


def fetch_ros_team_values(
    client: HttpClient,
    snapshot: LeagueSnapshot,
    players: dict[str, PlayerIdentity],
) -> tuple[dict[int, float], list[int], list[str]]:
    """Average each roster's best legal projected lineup over remaining weeks."""
    warnings: list[str] = []
    successful_weeks: list[int] = []
    weekly_totals = {team.roster_id: [] for team in snapshot.teams}
    slots = [
        "QB" if slot == "SUPER_FLEX" and not snapshot.is_superflex else slot
        for slot in snapshot.roster_positions
        if slot in {"QB", "RB", "WR", "TE", "FLEX", "SUPER_FLEX"}
    ]

    for week in ros_projection_weeks(snapshot):
        try:
            projections = fetch_weekly_projections(client, snapshot.season, week)
        except DataSourceError as exc:
            warnings.append(f"Sleeper Week {week} projections unavailable: {exc}")
            continue

        projected_values: dict[str, float] = {}
        for player_id, row in projections.items():
            identity = players.get(player_id)
            if identity is None or identity.position not in OFFENSE:
                continue
            value = projection_fantasy_points(
                row,
                snapshot.scoring_settings,
                position=identity.position,
            )
            if value > 0:
                projected_values[player_id] = value

        if not projected_values:
            warnings.append(
                f"Sleeper Week {week} had no mapped offensive projections; "
                "week omitted from ROS average."
            )
            continue

        week_values: dict[int, float] = {}
        complete = True
        for team in snapshot.teams:
            # Taxi players are not eligible to contribute unless activated.
            # Reserve/IR players remain roster assets for future weeks and can
            # contribute when that future week's provider projection returns.
            eligible_ids = [
                pid for pid in team.player_ids if pid not in set(team.taxi_player_ids)
            ]
            lineup = optimal_projected_lineup(
                eligible_ids,
                slots,
                players,
                projected_values,
            )
            if len(lineup) != len(slots):
                complete = False
                break
            week_values[team.roster_id] = sum(
                projected_values[player_id] for player_id in lineup
            )
        if not complete:
            warnings.append(
                f"Sleeper Week {week} did not support a complete legal projected "
                "lineup for every roster; week omitted from ROS average."
            )
            continue

        successful_weeks.append(week)
        for roster_id, total in week_values.items():
            weekly_totals[roster_id].append(total)

    if not successful_weeks:
        return {}, [], warnings

    values = {
        roster_id: mean(totals)
        for roster_id, totals in weekly_totals.items()
        if totals
    }
    expected = {team.roster_id for team in snapshot.teams}
    if set(values) != expected or any(value <= 0 for value in values.values()):
        warnings.append(
            "ROS projection coverage was incomplete; using the legacy "
            "starter-ranking fallback."
        )
        return {}, successful_weeks, warnings
    return values, successful_weeks, warnings
