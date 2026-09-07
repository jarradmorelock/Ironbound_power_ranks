from __future__ import annotations

import unittest
from types import SimpleNamespace

from ironbound_rankings.discord import build_message, escape_discord, parse_tag_ids
from ironbound_rankings.render import _draw_component_values, safe_chart_text
from ironbound_rankings.sleeper import _future_pick_ownership
from ironbound_rankings.sources import _starter_book_from_metadata, parse_pick_asset


class SourceParsingTests(unittest.TestCase):
    def test_parses_generic_future_pick(self) -> None:
        self.assertEqual(parse_pick_asset("2027 Mid 1st"), (2027, "mid", 1))

    def test_does_not_treat_exact_rookie_slot_as_future_pick(self) -> None:
        self.assertIsNone(parse_pick_asset("2026 Pick 1.01"))

    def test_starter_book_uses_adp_or_ros_and_excludes_unavailable_players(self) -> None:
        rows = [
            {
                "sleeper_id": "healthy",
                "position": "QB",
                "avg_adp": 1,
                "avg_ros": 50,
                "injury_status": "",
            },
            {
                "sleeper_id": "riser",
                "position": "RB",
                "avg_adp": 25,
                "avg_ros": 2,
                "injury_status": None,
            },
            {
                "sleeper_id": "unranked",
                "position": "WR",
                "avg_adp": 0,
                "avg_ros": None,
                "injury_status": "",
            },
            {
                "sleeper_id": "injured",
                "position": "TE",
                "avg_adp": 3,
                "avg_ros": 3,
                "injury_status": "IR",
            },
        ]

        adp = _starter_book_from_metadata(rows, starter_metric="adp")
        ros = _starter_book_from_metadata(rows, starter_metric="ros")

        self.assertEqual(adp.name, "Dynasty Daddy ADP")
        self.assertEqual(adp.player_values["healthy"], 499)
        self.assertEqual(ros.player_values["healthy"], 450)
        self.assertEqual(ros.player_values["riser"], 498)
        self.assertEqual(adp.player_values["unranked"], 400)
        self.assertNotIn("injured", adp.player_values)


class SleeperPickTests(unittest.TestCase):
    def test_traded_pick_moves_to_current_owner(self) -> None:
        ownership = _future_pick_ownership(
            roster_ids=[1, 2],
            traded_picks=[
                {"season": "2027", "round": 1, "roster_id": 1, "owner_id": 2}
            ],
            season=2026,
            in_season=True,
            draft_rounds=2,
        )
        team_one_picks = {(pick.year, pick.round, pick.original_roster_id) for pick in ownership[1]}
        team_two_picks = {(pick.year, pick.round, pick.original_roster_id) for pick in ownership[2]}
        self.assertNotIn((2027, 1, 1), team_one_picks)
        self.assertIn((2027, 1, 1), team_two_picks)

    def test_only_tracks_next_three_classes_in_season(self) -> None:
        ownership = _future_pick_ownership(
            roster_ids=[1],
            traded_picks=[],
            season=2026,
            in_season=True,
            draft_rounds=1,
        )
        self.assertEqual([pick.year for pick in ownership[1]], [2027, 2028, 2029])


class DiscordTests(unittest.TestCase):
    def test_parses_json_or_comma_separated_tag_ids(self) -> None:
        self.assertEqual(parse_tag_ids('["123", "456"]'), ["123", "456"])
        self.assertEqual(parse_tag_ids("123, 456"), ["123", "456"])

    def test_escapes_mentions_and_markdown(self) -> None:
        self.assertEqual(escape_discord("@Team *One*"), "＠Team \\*One\\*")

    def test_chart_text_normalizes_decorative_unicode(self) -> None:
        self.assertEqual(safe_chart_text("卄𝚊𝚙𝚙𝚢 卄𝚒𝚙𝚙𝚒𝚎𝚜™"), "Happy Hippies")
        self.assertEqual(safe_chart_text("🇵🇭 Barangay 828 🇵🇭"), "Barangay 828")

    def test_playoff_odds_stay_in_the_forecast_image_not_the_team_text(self) -> None:
        result = SimpleNamespace(
            league=SimpleNamespace(week=2, season=2026, is_superflex=False),
            teams=[
                SimpleNamespace(
                    rank=1,
                    team_name="Alpha",
                    record="1-0",
                    score=72.5,
                    movement=2,
                    make_playoffs_pct=88.0,
                    win_championship_pct=24.0,
                )
            ],
            dynasty_sources=["Market"],
            lineup_sources=["Dynasty Daddy ROS"],
            market_weight=0.50,
            lineup_weight=0.30,
            season_weight=0.20,
            has_season_results=True,
            record_guardrail_active=False,
            forecast_simulations=10_000,
            forecast_model="Elo-adjusted Dynasty Daddy ROS",
        )
        config = SimpleNamespace(brand="IRONBOUND", publication="IRONBOUND WEEKLY")

        _thread, content = build_message(result, config)

        self.assertIn("1-0 · 72.5 ▲2", content)
        self.assertNotIn("PO 88%", content)
        self.assertNotIn("TITLE 24%", content)


class _FakeLabel:
    def set_path_effects(self, effects) -> None:
        self.effects = effects


class _FakeAxes:
    def __init__(self) -> None:
        self.labels = []

    def text(self, x, y, value, **kwargs):
        self.labels.append((x, y, value, kwargs))
        return _FakeLabel()


class RenderTests(unittest.TestCase):
    def test_component_values_are_centered_inside_visible_segments(self) -> None:
        axes = _FakeAxes()

        _draw_component_values(
            axes,
            y=3,
            values=(40.0, 12.0, 8.0),
            has_season_results=False,
            text_color="#ffffff",
            outline_color="#000000",
        )

        self.assertEqual(
            [(x, y, value) for x, y, value, _ in axes.labels],
            [(20.0, 3, "40.0"), (46.0, 3, "12.0")],
        )


if __name__ == "__main__":
    unittest.main()
