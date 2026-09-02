"""Tests for the injectable Phase 13 utility clock boundary."""

from __future__ import annotations

import unittest
from datetime import UTC

from project_akiha.core.utilities import SystemUtilityClock, UtilityClock


class UtilityClockTest(unittest.TestCase):
    def test_system_clock_exposes_aware_utc_and_monotonic_time(self) -> None:
        clock = SystemUtilityClock()

        before = clock.monotonic_seconds()
        now = clock.now_utc()
        after = clock.monotonic_seconds()

        self.assertIsInstance(clock, UtilityClock)
        self.assertEqual(now.tzinfo, UTC)
        self.assertLessEqual(before, after)


if __name__ == "__main__":
    unittest.main()
