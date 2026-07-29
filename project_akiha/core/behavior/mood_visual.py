"""Map companion mood states to lightweight pet visual cues."""

from __future__ import annotations

from enum import StrEnum

from project_akiha.core.behavior.mood import CompanionMood


class MoodVisualCue(StrEnum):
    """UI-neutral visual cue names for companion mood."""

    NONE = "none"
    ATTENTION = "attention"
    WAITING = "waiting"
    RESTING = "resting"
    CHECKING_IN = "checking_in"
    SLEEPY = "sleepy"


class MoodVisualCueMapper:
    """Choose a small pet visual cue for the current companion mood."""

    def cue_for(self, mood: CompanionMood) -> MoodVisualCue:
        """Return the UI-neutral visual cue for a mood."""
        cues = {
            CompanionMood.CALM: MoodVisualCue.NONE,
            CompanionMood.ATTENTIVE: MoodVisualCue.ATTENTION,
            CompanionMood.WAITING: MoodVisualCue.WAITING,
            CompanionMood.RESTING: MoodVisualCue.RESTING,
            CompanionMood.CHECKING_IN: MoodVisualCue.CHECKING_IN,
            CompanionMood.SLEEPY: MoodVisualCue.SLEEPY,
        }
        return cues[mood]
