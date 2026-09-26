from __future__ import annotations

import random
import unittest

from ironbound_rankings.forecast import (
    _select_playoff_field,
    _simulate_regular_seasons,
    attach_playoff_forecast,
    rating_probabilities,
)
from ironbound_rankings.models import (
    LeagueMatchup,
    LeagueSnapshot,
    LeagueTeam,
    RankedTeam,
    RankingResult,
)


def _result() -> RankingResult:
    teams = [
        LeagueTeam(1, "1", "Alpha", "A", [], [], 0, 0, 0, 0, division=1),
        LeagueTeam(2, "2", "Bravo", "B", [], [], 0, 0, 0, 0, division=1),
        LeagueTeam(3, "3", "Charlie", "C", [], [], 0, 0, 0, 0, division=2),
        LeagueTeam(4, "4", "Delta", "D", [], [], 0, 0, 0, 0, division=2),
    ]
    schedule = [
        LeagueMatchup(week=1, matchup_id=1, roster_one=1, roster_two=4),
        LeagueMatchup(week=1, matchup_id=2, roster_one=2, roster_two=3),
        LeagueMatchup(week=2, matchup_id=1, roster_one=1, roster_two=3),
        LeagueMatchup(week=2, matchup_id=2, roster_one=2, roster_two=4),
        LeagueMatchup(week=3, matchup_id=1, roster_one=1, roster_two=2),
        LeagueMatchup(week=3, matchup_id=2, roster_one=3, roster_two=4),
    ]
    snapshot = LeagueSnapshot(
        league_id="forecast-test",
        league_name="Forecast Test",
        season=2026,
        week=1,
        is_superflex=False,
        ppr=0.5,
        roster_positions=["SUPER_FLEX"],
        teams=teams,
        start_week=1,
        playoff_week_start=4,
        playoff_teams=2,
        divisions=2,
        matchups=schedule,
    )
    ratings = {1: 1000.0, 2: 700.0, 3: 400.0, 4: 100.0}
    ranked = [
        RankedTeam(
            rank=roster_id,
            roster_id=roster_id,
            team_name=teams[roster_id - 1].team_name,
            owner_name=teams[roster_id - 1].owner_name,
            record="0-0",
            points_for=0,
            score=100 - roster_id,
            market_percentile=0,
            lineup_percentile=0,
            season_percentile=None,
            market_points=0,
            lineup_points=0,
            season_points=0,
            starter_rating=ratings[roster_id],
        )
        for roster_id in range(1, 5)
    ]
    return RankingResult(
        league=snapshot,
        teams=ranked,
        dynasty_sources=["Market"],
        lineup_sources=["Dynasty Daddy ADP"],
        has_season_results=False,
        generated_at="2026-09-07T12:00:00-04:00",
        market_weight=0.625,
        lineup_weight=0.375,
        season_weight=0,
        record_guardrail_active=False,
    )


def _raw_regular_counts(result: RankingResult, simulations: int) -> dict[int, dict[str, int]]:
    ratings = {team.roster_id: team.starter_rating for team in result.teams}
    probabilities = rating_probabilities(ratings)
    seed = f"{result.league.league_id}:{result.league.season}:{result.league.week}:{simulations}"
    return _simulate_regular_seasons(
        result.league,
        probabilities,
        simulations=simulations,
        rng=random.Random(seed),
    )


class ForecastTests(unittest.TestCase):
    def test_ironbound_field_has_four_division_winners_and_one_bye(self) -> None:
        team_ids = list(range(1, 17))
        divisions = [
            list(range(1, 5)),
            list(range(5, 9)),
            list(range(9, 13)),
            list(range(13, 17)),
        ]
        wins = {roster_id: float(17 - roster_id) for roster_id in team_ids}
        probabilities = {
            roster_id: (17 - roster_id) / 17 for roster_id in team_ids
        }

        qualifiers, division_winners, bye_teams = _select_playoff_field(
            team_ids,
            wins,
            probabilities,
            divisions,
            playoff_teams=7,
            rng=random.Random(1),
        )

        self.assertEqual(len(qualifiers), 7)
        self.assertEqual(len(division_winners), 4)
        self.assertEqual(len(bye_teams), 1)
        self.assertIn(bye_teams[0], division_winners)

    def test_simulation_fills_exact_playoff_field_and_one_champion(self) -> None:
        result = _result()
        attach_playoff_forecast(result, simulations=2_000)

        self.assertAlmostEqual(
            sum(team.make_playoffs_pct or 0 for team in result.teams),
            200.0,
            delta=0.2,
        )
        self.assertAlmostEqual(
            sum(team.win_division_pct or 0 for team in result.teams),
            200.0,
            delta=0.2,
        )
        self.assertAlmostEqual(
            sum(team.win_championship_pct or 0 for team in result.teams),
            100.0,
            delta=0.2,
        )
        self.assertGreater(
            result.teams[0].make_playoffs_pct,
            result.teams[-1].make_playoffs_pct,
        )
        self.assertEqual(result.forecast_simulations, 2_000)
        self.assertEqual(result.forecast_model, "Dynasty Daddy ADP")

    def test_forecast_is_repeatable_for_the_same_week(self) -> None:
        first = _result()
        second = _result()

        attach_playoff_forecast(first, simulations=1_000)
        attach_playoff_forecast(second, simulations=1_000)

        first_values = [
            (team.projected_record, team.make_playoffs_pct, team.win_championship_pct)
            for team in first.teams
        ]
        second_values = [
            (team.projected_record, team.make_playoffs_pct, team.win_championship_pct)
            for team in second.teams
        ]
        self.assertEqual(first_values, second_values)

    def test_week_one_forecast_uses_eighty_two_percent_raw_confidence(self) -> None:
        result = _result()
        result.league.playoff_week_start = 15
        simulations = 2_000
        counts = _raw_regular_counts(result, simulations)
        raw = counts[1]["playoffs"] / simulations * 100.0
        baseline = result.league.playoff_teams / len(result.teams) * 100.0

        attach_playoff_forecast(result, simulations=simulations)

        expected = round(baseline + 0.82 * (raw - baseline), 1)
        self.assertEqual(result.teams[0].make_playoffs_pct, expected)

    def test_soft_calibration_decreases_incrementally_each_week(self) -> None:
        result = _result()
        result.league.playoff_week_start = 15
        result.league.week = 4
        simulations = 2_000
        counts = _raw_regular_counts(result, simulations)
        raw = counts[1]["playoffs"] / simulations * 100.0
        baseline = result.league.playoff_teams / len(result.teams) * 100.0
        progress = (result.league.week - result.league.start_week) / 14.0
        baseline_share = 0.18 * (1.0 - progress / 0.5)

        attach_playoff_forecast(result, simulations=simulations)

        expected = round(baseline + (1.0 - baseline_share) * (raw - baseline), 1)
        self.assertEqual(result.teams[0].make_playoffs_pct, expected)
        self.assertLess(baseline_share, 0.18)
        self.assertGreater(baseline_share, 0.0)

    def test_soft_calibration_is_gone_by_midseason(self) -> None:
        result = _result()
        result.league.playoff_week_start = 15
        result.league.week = 8
        simulations = 2_000
        counts = _raw_regular_counts(result, simulations)

        attach_playoff_forecast(result, simulations=simulations)

        for team in result.teams:
            raw = round(counts[team.roster_id]["playoffs"] / simulations * 100.0, 1)
            self.assertEqual(team.make_playoffs_pct, raw)


if __name__ == "__main__":
    unittest.main()
