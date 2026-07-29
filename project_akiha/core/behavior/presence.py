"""User-facing companion presence text."""

from __future__ import annotations

from project_akiha.core.behavior.mood import CompanionMood


class CompanionPresenceMapper:
    """Map companion mood to short user-facing presence text."""

    def text_for(self, mood: CompanionMood) -> str:
        """Return a compact presence phrase for the current mood."""
        labels = {
            CompanionMood.CALM: "Akiha is calm.",
            CompanionMood.ATTENTIVE: "Akiha is paying attention.",
            CompanionMood.WAITING: "Akiha is waiting nearby.",
            CompanionMood.RESTING: "Akiha is resting.",
            CompanionMood.CHECKING_IN: "Akiha is checking in.",
            CompanionMood.SLEEPY: "Akiha is sleepy.",
        }
        return labels[mood]
