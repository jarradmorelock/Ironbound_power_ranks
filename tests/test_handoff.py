import json
import tempfile
import unittest
from pathlib import Path

from ironbound_rankings.handoff import (
    build_editorial_handoff,
    write_editorial_handoff,
)
from ironbound_rankings.models import (
    LeagueConfig,
    LeagueSnapshot,
    LeagueTeam,
    RankedTeam,
    RankingResult,
    Theme,
)


class EditorialHandoffTests(unittest.TestCase):
    def _config(self):
        return LeagueConfig(
            key="main",
            league_id="123",
            brand="IRONBOUND",
            publication="IRONBOUND WEEKLY",
            quarterback_mode="one_qb",
            webhook_env="WEBHOOK",
            tags_env="TAGS",
            theme=Theme(
                background="#000000",
                panel="#111111",
                text="#ffffff",
                muted="#cccccc",
                market="#222222",
                lineup="#333333",
                season="#444444",
                accent="#555555",
            ),
        )

    def _result(self):
        snapshot = LeagueSnapshot(
            league_id="123",
            league_name="Ironbound",
            season=2026,
            week=2,
            is_superflex=False,
            ppr=0.5,
            roster_positions=["QB"],
            teams=[
                LeagueTeam(
                    roster_id=7,
                    owner_id="u7",
                    team_name="San Carlos FC",
                    owner_name="Manager",
                    player_ids=[],
                    picks=[],
                    wins=2,
                    losses=0,
                    ties=0,
                    points_for=300,
                )
            ],
        )
        team = RankedTeam(
            rank=1,
            roster_id=7,
            team_name="San Carlos FC",
            owner_name="Manager",
            record="2-0",
            points_for=300,
            score=91.2,
            market_percentile=90,
            lineup_percentile=92,
            season_percentile=95,
            market_points=31,
            lineup_points=41,
            season_points=19,
            starter_rating=450,
            projected_record="11-3",
            make_playoffs_pct=91.0,
            win_division_pct=62.0,
            first_round_bye_pct=31.0,
            make_final_pct=29.0,
            win_championship_pct=15.0,
            previous_rank=3,
        )
        result = RankingResult(
            league=snapshot,
            teams=[team],
            dynasty_sources=["KeepTradeCut"],
            lineup_sources=["Dynasty Daddy ROS"],
            has_season_results=True,
            generated_at="2026-09-22T11:07:00-04:00",
            market_weight=0.35,
            lineup_weight=0.45,
            season_weight=0.20,
            record_guardrail_active=False,
            forecast_simulations=10000,
            forecast_model="Elo-adjusted Sleeper ROS scoring projections",
            ros_projection_weeks=[2, 3, 4],
        )
        result.remaining_schedule_strength = [
            {
                "roster_id": 7,
                "team": "San Carlos FC",
                "remaining_opponents": [2, 3],
                "average_opponent_index": 58.4,
                "difficulty_rank": 1,
                "grade": "F",
            }
        ]
        result.weekly_matchup_forecast = [
            {
                "week": 2,
                "matchup_id": 1,
                "roster_one": 7,
                "team_one": "San Carlos FC",
                "roster_two": 8,
                "team_two": "Blue Moose",
                "projected_score_one": 128.4,
                "projected_score_two": 124.1,
                "projected_total": 252.5,
                "favorite_roster_id": 7,
                "favorite_by": 4.3,
                "win_probability_one": 58.0,
                "simulations": 10000,
                "model": "projected-optimal legal lineup Monte Carlo",
                "optimal_lineup_one": ["p1"],
                "optimal_lineup_two": ["p2"],
            }
        ]
        return result

    def test_handoff_contains_rankings_and_playoff_forecast(self):
        payload = build_editorial_handoff(self._config(), self._result())
        self.assertEqual(payload["schema_version"], 3)
        self.assertEqual(payload["publication_key"], "ironbound_weekly")
        ranking = payload["official_power_rankings"][0]
        self.assertEqual(ranking["roster_id"], 7)
        self.assertEqual(ranking["rank"], 1)
        self.assertEqual(ranking["previous_rank"], 3)
        self.assertEqual(ranking["movement"], 2)
        self.assertEqual(ranking["score"], 91.2)
        self.assertEqual(
            ranking["components"],
            {
                "market_percentile": 90,
                "ros_starters_percentile": 92,
                "ros_scoring_percentile": 92,
                "season_results_percentile": 95,
                "market_points": 31,
                "ros_starters_points": 41,
                "ros_scoring_points": 41,
                "season_results_points": 19,
                "weights": {"market": 0.35, "ros_starters": 0.45, "ros_scoring": 0.45, "season_results": 0.20},
            },
        )
        self.assertEqual(payload["playoff_odds"][0]["playoff"], 91.0)
        self.assertEqual(payload["playoff_odds"][0]["championship"], 15.0)
        self.assertEqual(payload["remaining_schedule_strength"][0]["grade"], "F")
        self.assertEqual(payload["weekly_matchup_forecast"][0]["projected_total"], 252.5)
        self.assertEqual(payload["source_metadata"]["ranking_week"], 2)
        self.assertEqual(payload["source_metadata"]["results_through_week"], 1)
        self.assertEqual(payload["source_metadata"]["ros_projection_weeks"], [2, 3, 4])
        self.assertNotIn("usage", payload)
        self.assertNotIn("war", payload)
        self.assertNotIn("cwar", payload)
        self.assertTrue(any("usage" in note.lower() for note in payload["notes"]))

    def test_handoff_writer_emits_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rankings = root / "rankings.png"
            playoffs = root / "playoffs.png"
            rankings.write_bytes(b"ranking-image")
            playoffs.write_bytes(b"playoff-image")
            path = write_editorial_handoff(
                self._config(),
                self._result(),
                root / "handoff" / "main.json",
                power_rankings_image=rankings,
                playoff_forecast_image=playoffs,
            )
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], 3)
            self.assertEqual(payload["source_metadata"]["ranking_week"], 2)
            self.assertEqual(payload["source_metadata"]["results_through_week"], 1)
            self.assertEqual(payload["official_power_rankings"][0]["roster_id"], 7)
            self.assertEqual(payload["weekly_matchup_forecast"][0]["favorite_by"], 4.3)
            assets = payload["publication_assets"]
            self.assertEqual(
                assets["power_rankings"]["filename"],
                "ironbound_weekly-power-rankings.png",
            )
            self.assertEqual(
                assets["playoff_forecast"]["filename"],
                "ironbound_weekly-playoff-forecast.png",
            )
            self.assertEqual(assets["power_rankings"]["owner"], "Ironbound_power_ranks")
            self.assertEqual(
                (root / assets["power_rankings"]["repo_path"]).read_bytes(),
                b"ranking-image",
            )
            self.assertEqual(
                (root / assets["playoff_forecast"]["repo_path"]).read_bytes(),
                b"playoff-image",
            )


if __name__ == "__main__":
    unittest.main()
