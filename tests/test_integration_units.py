from __future__ import annotations

import unittest

from ironbound_rankings.discord import escape_discord, parse_tag_ids
from ironbound_rankings.render import safe_chart_text
from ironbound_rankings.sleeper import _future_pick_ownership
from ironbound_rankings.sources import parse_pick_asset


class SourceParsingTests(unittest.TestCase):
    def test_parses_generic_future_pick(self) -> None:
        self.assertEqual(parse_pick_asset("2027 Mid 1st"), (2027, "mid", 1))

    def test_does_not_treat_exact_rookie_slot_as_future_pick(self) -> None:
        self.assertIsNone(parse_pick_asset("2026 Pick 1.01"))


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


if __name__ == "__main__":
    unittest.main()
