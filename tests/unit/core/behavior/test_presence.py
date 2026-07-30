"""Tests for companion presence text mapping."""

from __future__ import annotations

import unittest

from project_akiha.core.behavior import CompanionMood, CompanionPresenceMapper


class CompanionPresenceMapperTest(unittest.TestCase):
    """Verify mood states map to compact user-facing text."""

    def test_maps_each_mood_to_presence_text(self) -> None:
        mapper = CompanionPresenceMapper()

        self.assertEqual(mapper.text_for(CompanionMood.CALM), "Akiha is calm.")
        self.assertEqual(
            mapper.text_for(CompanionMood.ATTENTIVE),
            "Akiha is paying attention.",
        )
        self.assertEqual(
            mapper.text_for(CompanionMood.WAITING),
            "Akiha is waiting nearby.",
        )
        self.assertEqual(mapper.text_for(CompanionMood.RESTING), "Akiha is resting.")
        self.assertEqual(
            mapper.text_for(CompanionMood.CHECKING_IN),
            "Akiha is checking in.",
        )
        self.assertEqual(mapper.text_for(CompanionMood.SLEEPY), "Akiha is sleepy.")
        self.assertEqual(
            mapper.text_for(CompanionMood.VOICE_LISTENING),
            "Akiha is listening.",
        )
        self.assertEqual(
            mapper.text_for(CompanionMood.VOICE_THINKING),
            "Akiha is thinking.",
        )
        self.assertEqual(
            mapper.text_for(CompanionMood.VOICE_SPEAKING),
            "Akiha is speaking.",
        )
        self.assertEqual(
            mapper.text_for(CompanionMood.VOICE_MUTED),
            "Akiha's voice is muted.",
        )
        self.assertEqual(
            mapper.text_for(CompanionMood.VOICE_ERROR),
            "Akiha's voice needs attention.",
        )


if __name__ == "__main__":
    unittest.main()
