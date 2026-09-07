"""Tests for the magazine email package."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from ironbound_rankings.mailer import build_power_rankings_email, parse_recipients


EASTERN = ZoneInfo("America/New_York")


class MailerTests(unittest.TestCase):
    def test_parses_one_or_multiple_recipients(self) -> None:
        self.assertEqual(parse_recipients("one@example.com"), ["one@example.com"])
        self.assertEqual(
            parse_recipients("one@example.com; two@example.com,three@example.com"),
            ["one@example.com", "two@example.com", "three@example.com"],
        )

    def test_builds_weekly_email_with_two_images_per_league(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            configs = [
                SimpleNamespace(key="main", brand="IRONBOUND"),
                SimpleNamespace(key="free", brand="UNBOUND"),
            ]
            for config in configs:
                output = root / "exports" / config.key
                output.mkdir(parents=True)
                (output / "latest.png").write_bytes(b"power")
                (output / "latest-playoffs.png").write_bytes(b"playoffs")
                (output / "latest.json").write_text(
                    json.dumps({"league": {"week": 3, "season": 2026}}),
                    encoding="utf-8",
                )

            message = build_power_rankings_email(
                configs,
                sender="publisher@example.com",
                recipients=["archive@example.com"],
                generated_at=datetime(2026, 9, 22, 11, 7, tzinfo=EASTERN),
                root=root,
            )

            self.assertEqual(
                message["Subject"],
                "Ironbound Power Rankings — Week 3 — Tuesday Edition",
            )
            self.assertEqual(message["To"], "archive@example.com")
            attachments = list(message.iter_attachments())
            self.assertEqual(len(attachments), 4)
            self.assertEqual(
                [attachment.get_filename() for attachment in attachments],
                [
                    "main-power-rankings-week-3.png",
                    "main-playoff-forecast-week-3.png",
                    "free-power-rankings-week-3.png",
                    "free-playoff-forecast-week-3.png",
                ],
            )


if __name__ == "__main__":
    unittest.main()
