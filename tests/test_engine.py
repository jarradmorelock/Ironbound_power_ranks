from __future__ import annotations

import unittest

from ironbound_rankings.engine import (
    optimal_lineup_value,
    percentile_scores,
    rank_league,
    ranking_weights,
)
from ironbound_rankings.models import (
    LeagueSnapshot,
    LeagueTeam,
    PlayerIdentity,
    ValueBook,
)


def player(player_id: str, position: str) -> PlayerIdentity:
    return PlayerIdentity(player_id, player_id, player_id, position)


class EngineTests(unittest.TestCase):
    def test_percentiles_handle_ties(self) -> None:
        result = percentile_scores({1: 10, 2: 20, 3: 20, 4: 40})
        self.assertEqual(result[1], 0)
        self.assertAlmostEqual(result[2], 50)
        self.assertAlmostEqual(result[3], 50)
        self.assertEqual(result[4], 100)

    def test_equal_percentiles_are_neutral(self) -> None:
        self.assertEqual(percentile_scores({1: 7, 2: 7}), {1: 50, 2: 50})

    def test_lineup_optimizer_reserves_running_backs_for_required_slots(self) -> None:
        players = {
            "qb": player("qb", "QB"),
            "rb1": player("rb1", "RB"),
            "rb2": player("rb2", "RB"),
            "wr": player("wr", "WR"),
        }
        values = {"qb": 100, "rb1": 90, "rb2": 80, "wr": 70}
        total = optimal_lineup_value(
            list(players), ["RB", "FLEX", "SUPER_FLEX"], players, values
        )
        self.assertEqual(total, 270)

    def test_results_affect_in_season_rankings(self) -> None:
        players = {
            "a": player("a", "QB"),
            "b": player("b", "QB"),
        }
        teams = [
            LeagueTeam(1, "1", "Alpha", "A", ["a"], [], 0, 1, 0, 100),
            LeagueTeam(2, "2", "Bravo", "B", ["b"], [], 1, 0, 0, 100),
        ]
        snapshot = LeagueSnapshot(
            "league", "League", 2026, 2, True, 0.5, ["SUPER_FLEX"], teams
        )
        books = [
            ValueBook("Dynasty", "dynasty", {"a": 100, "b": 100}),
            ValueBook("Redraft", "lineup", {"a": 100, "b": 100}),
        ]
        result = rank_league(snapshot, players, books)
        self.assertEqual(result.teams[0].team_name, "Bravo")
        self.assertGreater(result.teams[0].score, result.teams[1].score)
        self.assertTrue(result.has_season_results)

    def test_movement_compares_with_the_previous_published_order(self) -> None:
        players = {
            "a": player("a", "QB"),
            "b": player("b", "QB"),
        }
        teams = [
            LeagueTeam(1, "1", "Alpha", "A", ["a"], [], 0, 0, 0, 0),
            LeagueTeam(2, "2", "Bravo", "B", ["b"], [], 0, 0, 0, 0),
        ]
        snapshot = LeagueSnapshot(
            "league", "League", 2026, 1, False, 0.5, ["SUPER_FLEX"], teams
        )
        books = [
            ValueBook("Dynasty", "dynasty", {"a": 200, "b": 100}),
            ValueBook("ADP", "lineup", {"a": 200, "b": 100}),
        ]

        result = rank_league(
            snapshot,
            players,
            books,
            previous_ranks={"1": 2, "2": 1},
        )

        self.assertEqual(result.teams[0].team_name, "Alpha")
        self.assertEqual(result.teams[0].movement, 1)
        self.assertEqual(result.teams[1].movement, -1)

    def test_preseason_ignores_zero_records(self) -> None:
        players = {
            "a": player("a", "QB"),
            "b": player("b", "QB"),
        }
        teams = [
            LeagueTeam(1, "1", "Alpha", "A", ["a"], [], 0, 0, 0, 0),
            LeagueTeam(2, "2", "Bravo", "B", ["b"], [], 0, 0, 0, 0),
        ]
        snapshot = LeagueSnapshot(
            "league", "League", 2026, 1, True, 0.5, ["SUPER_FLEX"], teams
        )
        books = [
            ValueBook("Dynasty", "dynasty", {"a": 200, "b": 100}),
            ValueBook("Redraft", "lineup", {"a": 200, "b": 100}),
        ]
        result = rank_league(snapshot, players, books)
        self.assertEqual(result.teams[0].team_name, "Alpha")
        self.assertFalse(result.has_season_results)
        self.assertIsNone(result.teams[0].season_percentile)

    def test_results_gain_weight_as_the_season_progresses(self) -> None:
        self.assertEqual(ranking_weights(0), (0.45, 0.55, 0.0))
        self.assertEqual(ranking_weights(2), (0.35, 0.45, 0.20))
        self.assertEqual(ranking_weights(5), (0.30, 0.40, 0.30))
        self.assertEqual(ranking_weights(10), (0.25, 0.35, 0.40))

    def test_large_late_season_record_gap_limits_market_value_lead(self) -> None:
        players = {
            "market": player("market", "QB"),
            "winner": player("winner", "QB"),
        }
        teams = [
            LeagueTeam(1, "1", "Market Team", "A", ["market"], [], 7, 7, 0, 1400),
            LeagueTeam(2, "2", "Winning Team", "B", ["winner"], [], 12, 2, 0, 1200),
        ]
        snapshot = LeagueSnapshot(
            "league", "League", 2026, 15, True, 0.5, ["SUPER_FLEX"], teams
        )
        books = [
            ValueBook("Dynasty", "dynasty", {"market": 100, "winner": 1}),
            ValueBook("Redraft", "lineup", {"market": 100, "winner": 1}),
        ]

        result = rank_league(snapshot, players, books)
        by_name = {team.team_name: team for team in result.teams}

        self.assertTrue(result.record_guardrail_active)
        self.assertTrue(by_name["Market Team"].record_guardrail_applied)
        self.assertLessEqual(
            by_name["Market Team"].score - by_name["Winning Team"].score,
            10.0,
        )

    def test_one_qb_league_treats_sleeper_superflex_slot_as_qb_only(self) -> None:
        players = {
            "alpha_qb": player("alpha_qb", "QB"),
            "alpha_rb": player("alpha_rb", "RB"),
            "bravo_qb": player("bravo_qb", "QB"),
            "bravo_rb": player("bravo_rb", "RB"),
        }
        teams = [
            LeagueTeam(
                1, "1", "Alpha", "A", ["alpha_qb", "alpha_rb"], [], 0, 0, 0, 0
            ),
            LeagueTeam(
                2, "2", "Bravo", "B", ["bravo_qb", "bravo_rb"], [], 0, 0, 0, 0
            ),
        ]
        snapshot = LeagueSnapshot(
            "league", "League", 2026, 1, False, 0.5, ["SUPER_FLEX"], teams
        )
        books = [
            ValueBook(
                "Dynasty",
                "dynasty",
                {"alpha_qb": 1, "alpha_rb": 1, "bravo_qb": 1, "bravo_rb": 1},
            ),
            ValueBook(
                "Redraft",
                "lineup",
                {
                    "alpha_qb": 10,
                    "alpha_rb": 100,
                    "bravo_qb": 90,
                    "bravo_rb": 1,
                },
            ),
        ]

        result = rank_league(snapshot, players, books)

        self.assertEqual(result.teams[0].team_name, "Bravo")


if __name__ == "__main__":
    unittest.main()
