"""Sanitized, short-lived context for constrained intent interpretation."""

from __future__ import annotations

import re
from dataclasses import dataclass

_ACTION_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{1,79}$")
_APPLICATION_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{1,39}$")
_SPOTIFY_STATES = frozenset({"unknown", "playing", "paused"})


@dataclass(frozen=True, slots=True)
class IntentContextSnapshot:
    """Privacy-safe action state without paths, content, or conversation text."""

    recent_action_id: str = ""
    recent_application_id: str = ""
    spotify_playback_state: str = "unknown"
    has_recent_spotify_activity: bool = False
    has_recent_directory: bool = False

    def __post_init__(self) -> None:
        if self.recent_action_id and not _ACTION_ID_PATTERN.fullmatch(
            self.recent_action_id
        ):
            raise ValueError("recent intent action ID is invalid.")
        if self.recent_application_id and not _APPLICATION_ID_PATTERN.fullmatch(
            self.recent_application_id
        ):
            raise ValueError("recent intent application ID is invalid.")
        if self.spotify_playback_state not in _SPOTIFY_STATES:
            raise ValueError("Spotify playback context state is invalid.")

    @property
    def has_action_context(self) -> bool:
        return bool(
            self.recent_action_id
            or self.recent_application_id
            or self.has_recent_spotify_activity
            or self.has_recent_directory
        )

    def render_for_provider(self) -> str:
        """Render bounded labels only; never local targets or conversation content."""
        return "\n".join(
            (
                f"recent_action={self.recent_action_id or 'none'}",
                f"recent_application={self.recent_application_id or 'none'}",
                f"spotify_state={self.spotify_playback_state}",
                "recent_spotify="
                + ("yes" if self.has_recent_spotify_activity else "no"),
                "recent_directory=" + ("yes" if self.has_recent_directory else "no"),
            )
        )
