"""Deterministic Sleeper schedule and playoff simulations."""

from __future__ import annotations

from math import erf, floor, sqrt
import random
from statistics import mean, pstdev

from .models import LeagueMatchup, LeagueSnapshot, RankingResult


DEFAULT_SIMULATIONS = 10_000
MIN_GAME_PROBABILITY = 0.05
MAX_GAME_PROBABILITY = 0.95


def attach_playoff_forecast(
    result: RankingResult, *, simulations: int = DEFAULT_SIMULATIONS
) -> None:
    """Attach projected records and Monte Carlo playoff odds to ranked teams."""
    if simulations <= 0 or len(result.teams) < 2:
        return

    snapshot = result.league
    ratings = {team.roster_id: team.starter_rating for team in result.teams}
    completed_games = max((team.games for team in snapshot.teams), default=0)
    if completed_games:
        ratings = elo_adjusted_ratings(snapshot, ratings)
    probabilities = rating_probabilities(ratings)
    projected_records = projected_records_from_schedule(snapshot, probabilities)
    seed = f"{snapshot.league_id}:{snapshot.season}:{snapshot.week}:{simulations}"
    rng = random.Random(seed)

    if snapshot.week >= snapshot.playoff_week_start and snapshot.playoff_bracket:
        counts = _simulate_active_playoffs(
            snapshot,
            probabilities,
            simulations=simulations,
            rng=rng,
        )
    else:
        counts = _simulate_regular_seasons(
            snapshot,
            probabilities,
            simulations=simulations,
            rng=rng,
        )

    for team in result.teams:
        forecast = counts[team.roster_id]
        team.projected_record = projected_records[team.roster_id]
        team.make_playoffs_pct = _percentage(forecast["playoffs"], simulations)
        team.win_division_pct = _percentage(forecast["division"], simulations)
        team.first_round_bye_pct = _percentage(forecast["bye"], simulations)
        team.make_final_pct = _percentage(forecast["final"], simulations)
        team.win_championship_pct = _percentage(forecast["champion"], simulations)

    result.forecast_simulations = simulations
    starter_source = result.lineup_sources[0] if result.lineup_sources else "starter"
    result.forecast_model = (
        f"Elo-adjusted {starter_source}" if completed_games else starter_source
    )


def rating_probabilities(ratings: dict[int, float]) -> dict[int, float]:
    """Convert team ratings to the same normal-CDF signal used for matchups."""
    if not ratings:
        return {}
    values = list(ratings.values())
    average = mean(values)
    deviation = pstdev(values)
    if deviation <= 0:
        return {roster_id: 0.5 for roster_id in ratings}
    return {
        roster_id: 0.5 * (1.0 + erf(((rating - average) / deviation) / sqrt(2.0)))
        for roster_id, rating in ratings.items()
    }


def elo_adjusted_ratings(
    snapshot: LeagueSnapshot, ratings: dict[int, float]
) -> dict[int, float]:
    """Adjust starter ratings with completed Sleeper matchup results."""
    adjusted = dict(ratings)
    completed = sorted(
        (matchup for matchup in snapshot.matchups if matchup.week < snapshot.week),
        key=lambda matchup: (matchup.week, matchup.matchup_id),
    )
    for matchup in completed:
        one = matchup.roster_one
        two = matchup.roster_two
        if one not in adjusted or two not in adjusted:
            continue
        if matchup.points_one == matchup.points_two == 0:
            continue
        expected_one = 1.0 / (1.0 + 10 ** ((adjusted[two] - adjusted[one]) / 400.0))
        if matchup.points_one > matchup.points_two:
            actual_one = 1.0
        elif matchup.points_one < matchup.points_two:
            actual_one = 0.0
        else:
            actual_one = 0.5
        k_value = min(40.0, max(10.0, abs(matchup.points_one - matchup.points_two)))
        change = k_value * (actual_one - expected_one)
        adjusted[one] += change
        adjusted[two] -= change
    return adjusted


def projected_records_from_schedule(
    snapshot: LeagueSnapshot, probabilities: dict[int, float]
) -> dict[int, str]:
    expected_wins = {
        team.roster_id: team.wins + team.ties * 0.5 for team in snapshot.teams
    }
    start_week = max(snapshot.start_week, snapshot.week)
    for matchup in _remaining_regular_season(snapshot, start_week):
        chance_one = game_probability(
            probabilities[matchup.roster_one], probabilities[matchup.roster_two]
        )
        expected_wins[matchup.roster_one] += chance_one
        expected_wins[matchup.roster_two] += 1.0 - chance_one

    regular_games = max(0, snapshot.playoff_week_start - snapshot.start_week)
    projected: dict[int, str] = {}
    for team in snapshot.teams:
        wins = min(regular_games, int(floor(expected_wins[team.roster_id] + 0.5)))
        projected[team.roster_id] = f"{wins}-{max(0, regular_games - wins)}"
    return projected


def game_probability(one: float, two: float) -> float:
    probability = 0.5 + (one - two) / 2.0
    return min(MAX_GAME_PROBABILITY, max(MIN_GAME_PROBABILITY, probability))


def _simulate_regular_seasons(
    snapshot: LeagueSnapshot,
    probabilities: dict[int, float],
    *,
    simulations: int,
    rng: random.Random,
) -> dict[int, dict[str, int]]:
    counts = _empty_counts(snapshot)
    base_wins = {
        team.roster_id: team.wins + team.ties * 0.5 for team in snapshot.teams
    }
    start_week = max(snapshot.start_week, snapshot.week)
    remaining = _remaining_regular_season(snapshot, start_week)
    team_ids = list(base_wins)
    divisions = _division_groups(snapshot)

    for _ in range(simulations):
        wins = dict(base_wins)
        for matchup in remaining:
            winner = _play_game(
                matchup.roster_one,
                matchup.roster_two,
                probabilities,
                rng,
            )
            wins[winner] += 1

        qualifiers, division_winners, bye_teams = _select_playoff_field(
            team_ids,
            wins,
            probabilities,
            divisions,
            playoff_teams=snapshot.playoff_teams,
            rng=rng,
        )
        for roster_id in qualifiers:
            counts[roster_id]["playoffs"] += 1
        for roster_id in division_winners:
            counts[roster_id]["division"] += 1
        for roster_id in bye_teams:
            counts[roster_id]["bye"] += 1

        finalists, champion = _simulate_postseason(
            qualifiers,
            bye_teams,
            probabilities,
            rng,
            games_per_round=2 if snapshot.playoff_round_type == 2 else 1,
        )
        for roster_id in finalists:
            counts[roster_id]["final"] += 1
        if champion is not None:
            counts[champion]["champion"] += 1
    return counts


def _simulate_active_playoffs(
    snapshot: LeagueSnapshot,
    probabilities: dict[int, float],
    *,
    simulations: int,
    rng: random.Random,
) -> dict[int, dict[str, int]]:
    counts = _empty_counts(snapshot)
    entrants = _bracket_roster_ids(snapshot.playoff_bracket)
    eliminated = {
        int(row["l"])
        for row in snapshot.playoff_bracket
        if isinstance(row, dict) and isinstance(row.get("l"), int)
    }
    alive = [roster_id for roster_id in entrants if roster_id not in eliminated]
    first_round = {
        int(value)
        for row in snapshot.playoff_bracket
        if isinstance(row, dict) and int(row.get("r") or 0) == 1
        for value in (row.get("t1"), row.get("t2"))
        if isinstance(value, int)
    }
    initial_byes = [roster_id for roster_id in entrants if roster_id not in first_round]

    for roster_id in entrants:
        counts[roster_id]["playoffs"] = simulations
    for roster_id in initial_byes:
        counts[roster_id]["bye"] = simulations

    ordered_alive = sorted(alive, key=lambda roster_id: probabilities[roster_id], reverse=True)
    live_byes = [roster_id for roster_id in initial_byes if roster_id in alive]
    for _ in range(simulations):
        finalists, champion = _simulate_postseason(
            ordered_alive,
            live_byes if len(alive) == len(entrants) else [],
            probabilities,
            rng,
            games_per_round=2 if snapshot.playoff_round_type == 2 else 1,
        )
        for roster_id in finalists:
            counts[roster_id]["final"] += 1
        if champion is not None:
            counts[champion]["champion"] += 1
    return counts


def _remaining_regular_season(
    snapshot: LeagueSnapshot, start_week: int
) -> list[LeagueMatchup]:
    return [
        matchup
        for matchup in snapshot.matchups
        if start_week <= matchup.week < snapshot.playoff_week_start
    ]


def _division_groups(snapshot: LeagueSnapshot) -> list[list[int]]:
    if snapshot.divisions <= 1:
        return []
    groups: dict[int, list[int]] = {}
    for team in snapshot.teams:
        if team.division > 0:
            groups.setdefault(team.division, []).append(team.roster_id)
    return list(groups.values()) if len(groups) > 1 else []


def _select_playoff_field(
    team_ids: list[int],
    wins: dict[int, float],
    probabilities: dict[int, float],
    divisions: list[list[int]],
    *,
    playoff_teams: int,
    rng: random.Random,
) -> tuple[list[int], list[int], list[int]]:
    playoff_teams = min(len(team_ids), max(2, playoff_teams))
    division_winners: list[int] = []
    if divisions:
        division_winners = [
            _select_best(group, wins, probabilities, rng) for group in divisions
        ]
        if len(division_winners) > playoff_teams:
            division_winners = _rank_by_record(
                division_winners, wins, probabilities, rng
            )[:playoff_teams]

    remaining_spots = playoff_teams - len(division_winners)
    remaining = [roster_id for roster_id in team_ids if roster_id not in division_winners]
    wildcards = _rank_by_record(remaining, wins, probabilities, rng)[:remaining_spots]
    qualifiers = division_winners + wildcards

    bracket_size = 1 << (playoff_teams - 1).bit_length()
    bye_count = max(0, bracket_size - playoff_teams)
    bye_pool = division_winners if division_winners else qualifiers
    bye_teams = _rank_by_record(bye_pool, wins, probabilities, rng)[:bye_count]
    seeded = bye_teams + _rank_by_record(
        [roster_id for roster_id in qualifiers if roster_id not in bye_teams],
        wins,
        probabilities,
        rng,
    )
    return seeded, division_winners, bye_teams


def _rank_by_record(
    candidates: list[int],
    wins: dict[int, float],
    probabilities: dict[int, float],
    rng: random.Random,
) -> list[int]:
    remaining = list(candidates)
    ordered: list[int] = []
    while remaining:
        selected = _select_best(remaining, wins, probabilities, rng)
        ordered.append(selected)
        remaining.remove(selected)
    return ordered


def _select_best(
    candidates: list[int],
    wins: dict[int, float],
    probabilities: dict[int, float],
    rng: random.Random,
) -> int:
    best_record = max(wins[roster_id] for roster_id in candidates)
    tied = [roster_id for roster_id in candidates if wins[roster_id] == best_record]
    selected = tied[0]
    for challenger in tied[1:]:
        selected = _play_game(selected, challenger, probabilities, rng)
    return selected


def _simulate_postseason(
    qualifiers: list[int],
    bye_teams: list[int],
    probabilities: dict[int, float],
    rng: random.Random,
    *,
    games_per_round: int,
) -> tuple[list[int], int | None]:
    if not qualifiers:
        return [], None
    seed = {roster_id: index for index, roster_id in enumerate(qualifiers)}
    current = list(qualifiers)
    if len(current) > 2:
        non_byes = [roster_id for roster_id in current if roster_id not in bye_teams]
        first_round_winners = _play_round(
            non_byes, probabilities, rng, games_per_round=games_per_round
        )
        current = list(bye_teams) + first_round_winners
        current.sort(key=lambda roster_id: seed.get(roster_id, 999))

    while len(current) > 2:
        current = _play_round(
            current, probabilities, rng, games_per_round=games_per_round
        )
        current.sort(key=lambda roster_id: seed.get(roster_id, 999))

    finalists = list(current)
    if len(current) == 1:
        return finalists, current[0]
    champion = _play_series(
        current[0],
        current[1],
        probabilities,
        rng,
        games_per_round=games_per_round,
    )
    return finalists, champion


def _play_round(
    teams: list[int],
    probabilities: dict[int, float],
    rng: random.Random,
    *,
    games_per_round: int,
) -> list[int]:
    winners: list[int] = []
    start = 0
    if len(teams) % 2:
        winners.append(teams[0])
        start = 1
    available = teams[start:]
    for index in range(len(available) // 2):
        winners.append(
            _play_series(
                available[index],
                available[-1 - index],
                probabilities,
                rng,
                games_per_round=games_per_round,
            )
        )
    return winners


def _play_series(
    one: int,
    two: int,
    probabilities: dict[int, float],
    rng: random.Random,
    *,
    games_per_round: int,
) -> int:
    wins_one = 0
    wins_two = 0
    for _ in range(games_per_round):
        winner = _play_game(one, two, probabilities, rng)
        wins_one += winner == one
        wins_two += winner == two
    if wins_one == wins_two:
        return _play_game(one, two, probabilities, rng)
    return one if wins_one > wins_two else two


def _play_game(
    one: int,
    two: int,
    probabilities: dict[int, float],
    rng: random.Random,
) -> int:
    chance_one = game_probability(probabilities[one], probabilities[two])
    return one if rng.random() < chance_one else two


def _bracket_roster_ids(bracket: list[dict]) -> list[int]:
    roster_ids: list[int] = []
    for row in bracket:
        if not isinstance(row, dict):
            continue
        for key in ("t1", "t2", "w", "l"):
            value = row.get(key)
            if isinstance(value, int) and value not in roster_ids:
                roster_ids.append(value)
    return roster_ids


def _empty_counts(snapshot: LeagueSnapshot) -> dict[int, dict[str, int]]:
    return {
        team.roster_id: {
            "playoffs": 0,
            "division": 0,
            "bye": 0,
            "final": 0,
            "champion": 0,
        }
        for team in snapshot.teams
    }


def _percentage(count: int, simulations: int) -> float:
    return round(count / simulations * 100.0, 1)
