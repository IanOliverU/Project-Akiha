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
    VOICE_LISTENING = "voice_listening"
    VOICE_THINKING = "voice_thinking"
    VOICE_SPEAKING = "voice_speaking"
    VOICE_MUTED = "voice_muted"
    VOICE_ERROR = "voice_error"


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
            CompanionMood.VOICE_LISTENING: MoodVisualCue.VOICE_LISTENING,
            CompanionMood.VOICE_THINKING: MoodVisualCue.VOICE_THINKING,
            CompanionMood.VOICE_SPEAKING: MoodVisualCue.VOICE_SPEAKING,
            CompanionMood.VOICE_MUTED: MoodVisualCue.VOICE_MUTED,
            CompanionMood.VOICE_ERROR: MoodVisualCue.VOICE_ERROR,
        }
        return cues[mood]
