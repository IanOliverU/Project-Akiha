"""Tests for conservative context-bound Spotify speech recovery."""

from __future__ import annotations

import unittest

from project_akiha.services.contextual_spotify_intent import (
    ContextualSpotifyIntentResolver,
)


class ContextualSpotifyIntentResolverTest(unittest.TestCase):
    def setUp(self) -> None:
        self.resolver = ContextualSpotifyIntentResolver()

    def test_recovers_noisy_and_language_shifted_controls(self) -> None:
        pause = self.resolver.resolve("Paue MIZIK", playback_state="playing")
        resume = self.resolver.resolve(
            "Continua la música",
            playback_state="paused",
        )

        self.assertEqual(pause.action_id, "spotify.pause")
        self.assertEqual(resume.action_id, "spotify.resume")

    def test_uses_state_for_short_follow_up_but_not_unrelated_work(self) -> None:
        resume = self.resolver.resolve("Continue", playback_state="paused")
        unrelated = self.resolver.resolve(
            "Continue working on the project",
            playback_state="paused",
        )

        self.assertEqual(resume.action_id, "spotify.resume")
        self.assertIsNone(unrelated)

    def test_returns_clarification_for_competing_controls(self) -> None:
        result = self.resolver.resolve(
            "Pause or resume music",
            playback_state="paused",
        )

        self.assertTrue(result.clarification)
        self.assertFalse(result.action_id)

    def test_rejects_invalid_state(self) -> None:
        with self.assertRaises(ValueError):
            self.resolver.resolve("Pause music", playback_state="buffering")


if __name__ == "__main__":
    unittest.main()
