"""Tests for continuous cross-publication ranking history."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from ironbound_rankings.state import save_state


def _result(*, generated_at: str, ranks: list[tuple[int, int]]):
    return SimpleNamespace(
        league=SimpleNamespace(league_id="league-1"),
        generated_at=generated_at,
        teams=[
            SimpleNamespace(roster_id=roster_id, rank=rank)
            for roster_id, rank in ranks
        ],
    )


class StateTests(unittest.TestCase):
    def test_email_and_discord_share_ranks_but_keep_duplicate_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "main.json"
            path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "last_published_key": "2026-week-1",
                        "last_published_at": "saturday",
                        "rank_by_roster_id": {"1": 2},
                    }
                ),
                encoding="utf-8",
            )

            save_state(
                path,
                _result(generated_at="tuesday", ranks=[(1, 4)]),
                "2026-week-1",
                publication="email",
            )
            data = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(data["rank_by_roster_id"], {"1": 4})
            self.assertEqual(data["last_discord_published_key"], "2026-week-1")
            self.assertEqual(data["last_email_published_key"], "2026-week-1")
            self.assertNotIn("last_published_key", data)

            save_state(
                path,
                _result(generated_at="saturday-two", ranks=[(1, 3)]),
                "2026-week-2",
                publication="discord",
            )
            data = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(data["rank_by_roster_id"], {"1": 3})
            self.assertEqual(data["last_discord_published_key"], "2026-week-2")
            self.assertEqual(data["last_email_published_key"], "2026-week-1")


if __name__ == "__main__":
    unittest.main()
