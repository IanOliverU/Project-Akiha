"""Select exactly one explicit conversation runtime lane."""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Protocol


class ConversationRuntimeLane(StrEnum):
    """User-visible conversation runtimes supported by V6."""

    LOCAL_MODULAR = "local_modular"
    GEMINI_LIVE = "gemini_live"


class _ConversationRuntime(Protocol):
    @property
    def active(self) -> bool:
        """Return whether this runtime currently owns a conversation."""

    def start(self) -> bool:
        """Start this runtime after an explicit user request."""

    def end(self, reason: str = "user") -> bool:
        """End this runtime without starting another lane."""

    def close(self) -> None:
        """Release runtime resources during application shutdown."""


class ConversationRuntimeRouter:
    """Route Start/End to one selected lane without automatic fallback."""

    def __init__(
        self,
        *,
        selection_provider: Callable[[], str],
        local_runtime: _ConversationRuntime,
        hosted_runtime: _ConversationRuntime,
    ) -> None:
        self._selection_provider = selection_provider
        self._runtimes = {
            ConversationRuntimeLane.LOCAL_MODULAR: local_runtime,
            ConversationRuntimeLane.GEMINI_LIVE: hosted_runtime,
        }
        self._active_lane: ConversationRuntimeLane | None = None

    @property
    def active_lane(self) -> ConversationRuntimeLane | None:
        """Return the lane selected by the most recent successful Start."""
        return self._active_lane

    @property
    def active(self) -> bool:
        """Return whether the selected runtime still owns a conversation."""
        lane = self._active_lane
        return lane is not None and self._runtimes[lane].active

    @property
    def selected_lane(self) -> ConversationRuntimeLane:
        """Validate and return the lane currently selected in Settings."""
        try:
            return ConversationRuntimeLane(self._selection_provider())
        except ValueError as error:
            raise ValueError("Unknown conversation runtime selection.") from error

    def start(self) -> bool:
        """Start only the explicitly selected runtime."""
        if self.active:
            return False
        self._active_lane = None
        lane = self.selected_lane
        if not self._runtimes[lane].start():
            return False
        self._active_lane = lane
        return True

    def end(self, reason: str = "user") -> bool:
        """End the active runtime without invoking the other lane."""
        lane = self._active_lane
        if lane is None:
            return False
        ended = self._runtimes[lane].end(reason)
        if ended or not self._runtimes[lane].active:
            self._active_lane = None
        return ended

    def runtime_stopped(self, lane: ConversationRuntimeLane) -> None:
        """Forget an asynchronously stopped runtime without selecting fallback."""
        if self._active_lane is lane:
            self._active_lane = None

    def close(self) -> None:
        """Close both independent runtimes exactly once."""
        self._active_lane = None
        for runtime in self._runtimes.values():
            runtime.close()
