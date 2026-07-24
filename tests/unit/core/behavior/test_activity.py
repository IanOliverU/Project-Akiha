"""Tests for user activity tracking."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from project_akiha.core.behavior import ActivityState, ActivityTracker


class ActivityTrackerTest(unittest.TestCase):
    """Verify active/idle/away state inference."""

    def test_tracks_active_idle_and_away_states(self) -> None:
        start = datetime(2026, 7, 24, 10, 0, tzinfo=UTC)
        tracker = ActivityTracker(
            idle_after_seconds=300,
            away_after_seconds=900,
            initial_time=start,
        )

        self.assertEqual(tracker.snapshot(start).state, ActivityState.ACTIVE)
        self.assertEqual(
            tracker.snapshot(start + timedelta(seconds=300)).state,
            ActivityState.IDLE,
        )
        self.assertEqual(
            tracker.snapshot(start + timedelta(seconds=900)).state,
            ActivityState.AWAY,
        )

    def test_recording_activity_resets_idle_seconds(self) -> None:
        start = datetime(2026, 7, 24, 10, 0, tzinfo=UTC)
        tracker = ActivityTracker(
            idle_after_seconds=300,
            away_after_seconds=900,
            initial_time=start,
        )
        later = start + timedelta(seconds=901)

        snapshot = tracker.record_activity("chat", later)

        self.assertEqual(snapshot.state, ActivityState.ACTIVE)
        self.assertEqual(snapshot.idle_seconds, 0)
        self.assertEqual(snapshot.source, "chat")

    def test_rejects_invalid_thresholds(self) -> None:
        with self.assertRaises(ValueError):
            ActivityTracker(idle_after_seconds=60, away_after_seconds=60)


if __name__ == "__main__":
    unittest.main()
