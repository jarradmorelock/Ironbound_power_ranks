"""Tests for the delay-safe Eastern publication guard."""

from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from ironbound_rankings.publisher import (
    is_noon_eastern_schedule,
    is_tuesday_email_schedule,
)


EASTERN = ZoneInfo("America/New_York")


class ScheduleGuardTests(unittest.TestCase):
    def test_delayed_daylight_run_uses_1607_utc_trigger(self) -> None:
        delayed = datetime(2026, 9, 5, 13, 56, tzinfo=EASTERN)
        self.assertTrue(is_noon_eastern_schedule(delayed, "7 16 * * 6"))
        self.assertFalse(is_noon_eastern_schedule(delayed, "7 17 * * 6"))

    def test_delayed_standard_run_uses_1707_utc_trigger(self) -> None:
        delayed = datetime(2026, 12, 5, 14, 20, tzinfo=EASTERN)
        self.assertTrue(is_noon_eastern_schedule(delayed, "7 17 * * 6"))
        self.assertFalse(is_noon_eastern_schedule(delayed, "7 16 * * 6"))

    def test_wrong_day_is_rejected(self) -> None:
        sunday = datetime(2026, 9, 6, 12, 7, tzinfo=EASTERN)
        self.assertFalse(is_noon_eastern_schedule(sunday, "7 16 * * 6"))

    def test_manual_compatibility_remains_strictly_noon(self) -> None:
        noon = datetime(2026, 9, 5, 12, 30, tzinfo=EASTERN)
        late = datetime(2026, 9, 5, 13, 1, tzinfo=EASTERN)
        self.assertTrue(is_noon_eastern_schedule(noon, None))
        self.assertFalse(is_noon_eastern_schedule(late, None))

    def test_tuesday_email_uses_daylight_trigger(self) -> None:
        delayed = datetime(2026, 9, 8, 12, 42, tzinfo=EASTERN)
        self.assertTrue(is_tuesday_email_schedule(delayed, "7 15 * * 2"))
        self.assertFalse(is_tuesday_email_schedule(delayed, "7 16 * * 2"))

    def test_tuesday_email_uses_standard_trigger(self) -> None:
        delayed = datetime(2026, 12, 8, 13, 18, tzinfo=EASTERN)
        self.assertTrue(is_tuesday_email_schedule(delayed, "7 16 * * 2"))
        self.assertFalse(is_tuesday_email_schedule(delayed, "7 15 * * 2"))

    def test_tuesday_email_rejects_wrong_day(self) -> None:
        monday = datetime(2026, 9, 7, 11, 7, tzinfo=EASTERN)
        self.assertFalse(is_tuesday_email_schedule(monday, "7 15 * * 2"))


if __name__ == "__main__":
    unittest.main()
