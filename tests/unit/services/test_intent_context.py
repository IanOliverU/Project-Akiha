"""Tests for privacy-safe conversational intent context."""

from __future__ import annotations

import unittest

from project_akiha.services.intent_context import IntentContextSnapshot


class IntentContextSnapshotTest(unittest.TestCase):
    def test_renders_only_coarse_allowlisted_state(self) -> None:
        context = IntentContextSnapshot(
            recent_action_id="applications.launch",
            recent_application_id="discord",
            spotify_playback_state="paused",
            has_recent_spotify_activity=True,
            has_recent_directory=True,
        )

        rendered = context.render_for_provider()

        self.assertIn("recent_action=applications.launch", rendered)
        self.assertIn("recent_application=discord", rendered)
        self.assertIn("spotify_state=paused", rendered)
        self.assertNotIn("C:\\", rendered)
        self.assertNotIn("conversation", rendered)

    def test_rejects_unbounded_context_labels(self) -> None:
        with self.assertRaises(ValueError):
            IntentContextSnapshot(recent_action_id="open C:\\secret")
        with self.assertRaises(ValueError):
            IntentContextSnapshot(recent_application_id="../../powershell")
        with self.assertRaises(ValueError):
            IntentContextSnapshot(spotify_playback_state="buffering")


if __name__ == "__main__":
    unittest.main()
