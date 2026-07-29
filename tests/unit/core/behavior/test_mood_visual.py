"""Tests for mood visual cue mapping."""

from __future__ import annotations

import unittest

from project_akiha.core.behavior import (
    CompanionMood,
    MoodVisualCue,
    MoodVisualCueMapper,
)


class MoodVisualCueMapperTest(unittest.TestCase):
    """Verify companion moods map to lightweight pet visual cues."""

    def test_calm_mood_has_no_extra_visual_cue(self) -> None:
        self.assertEqual(
            MoodVisualCueMapper().cue_for(CompanionMood.CALM),
            MoodVisualCue.NONE,
        )

    def test_activity_moods_map_to_visible_cues(self) -> None:
        mapper = MoodVisualCueMapper()

        self.assertEqual(
            mapper.cue_for(CompanionMood.ATTENTIVE),
            MoodVisualCue.ATTENTION,
        )
        self.assertEqual(mapper.cue_for(CompanionMood.WAITING), MoodVisualCue.WAITING)
        self.assertEqual(mapper.cue_for(CompanionMood.RESTING), MoodVisualCue.RESTING)
        self.assertEqual(
            mapper.cue_for(CompanionMood.CHECKING_IN),
            MoodVisualCue.CHECKING_IN,
        )
        self.assertEqual(mapper.cue_for(CompanionMood.SLEEPY), MoodVisualCue.SLEEPY)


if __name__ == "__main__":
    unittest.main()
