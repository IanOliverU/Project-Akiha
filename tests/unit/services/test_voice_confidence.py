"""Tests for language-neutral speech confidence policy."""

from __future__ import annotations

import unittest

from project_akiha.services.voice_confidence import (
    transcript_requires_review,
    voice_confidence_level,
)


class VoiceConfidenceTest(unittest.TestCase):
    """Verify uncertainty changes submission policy, not transcript text."""

    def test_confidence_bands_are_stable(self) -> None:
        self.assertIsNone(voice_confidence_level(None))
        self.assertEqual(voice_confidence_level(0.2), "low")
        self.assertEqual(voice_confidence_level(0.6), "medium")
        self.assertEqual(voice_confidence_level(0.9), "high")

    def test_only_reported_low_confidence_requires_review(self) -> None:
        self.assertTrue(transcript_requires_review(0.2))
        self.assertFalse(transcript_requires_review(0.6))
        self.assertFalse(transcript_requires_review(None))


if __name__ == "__main__":
    unittest.main()
