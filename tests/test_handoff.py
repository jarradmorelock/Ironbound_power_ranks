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
        return RankingResult(
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
            forecast_model="Elo-adjusted Dynasty Daddy ROS",
        )

    def test_handoff_contains_rankings_and_playoff_forecast(self):
        payload = build_editorial_handoff(self._config(), self._result())
        self.assertEqual(payload["publication_key"], "ironbound_weekly")
        self.assertEqual(
            payload["official_power_rankings"][0],
            {
                "roster_id": 7,
                "team": "San Carlos FC",
                "rank": 1,
                "previous_rank": 3,
                "movement": 2,
                "score": 91.2,
            },
        )
        self.assertEqual(payload["playoff_odds"][0]["playoff"], 91.0)
        self.assertEqual(payload["playoff_odds"][0]["championship"], 15.0)
        self.assertNotIn("usage", payload)
        self.assertNotIn("war", payload)
        self.assertNotIn("cwar", payload)
        self.assertTrue(any("usage" in note.lower() for note in payload["notes"]))

    def test_handoff_writer_emits_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_editorial_handoff(
                self._config(), self._result(), Path(tmp) / "handoff" / "main.json"
            )
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["source_metadata"]["week"], 2)
            self.assertEqual(payload["official_power_rankings"][0]["roster_id"], 7)


if __name__ == "__main__":
    unittest.main()
