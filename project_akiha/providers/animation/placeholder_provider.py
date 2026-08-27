"""Placeholder frame provider for the Phase 1 painted pet."""

from __future__ import annotations

from project_akiha.core.state.animation import (
    AnimationClipId,
    AnimationSequenceId,
    AnimationState,
)
from project_akiha.providers.animation.base import AnimationFrame, AnimationSequence


class PlaceholderAnimationProvider:
    """Generate simple frame data until real sprite assets exist."""

    _available_states = frozenset(AnimationState)
    _cycle_length = 240
    _idle_bob_period = 24
    _idle_bob_offset = 4

    def available_states(self) -> frozenset[AnimationState]:
        """Return animation states supported by this provider."""
        return self._available_states

    def available_sequences(self) -> frozenset[AnimationSequenceId]:
        """Return no staged sequences until trusted artwork is supplied."""
        return frozenset()

    def sequence_for(self, sequence_id: AnimationSequenceId) -> AnimationSequence:
        """Reject unavailable staged sequences explicitly."""
        raise KeyError(f"Animation sequence is not declared: {sequence_id.value}.")

    def frame_for_clip(
        self,
        clip_id: AnimationClipId,
        frame_number: int,
    ) -> AnimationFrame:
        """Reject unavailable staged clips explicitly."""
        del frame_number
        raise KeyError(f"Animation clip is not declared: {clip_id.value}.")

    def clip_duration_ticks(self, clip_id: AnimationClipId) -> int:
        """Reject unavailable staged clip timing explicitly."""
        raise KeyError(f"Animation clip is not declared: {clip_id.value}.")

    def clip_loops(self, clip_id: AnimationClipId) -> bool:
        """Reject unavailable staged clip behavior explicitly."""
        raise KeyError(f"Animation clip is not declared: {clip_id.value}.")

    def frame_for(
        self,
        state: AnimationState,
        frame_number: int,
    ) -> AnimationFrame:
        """Return placeholder frame data for the requested state."""
        if state not in self._available_states:
            state = AnimationState.IDLE

        frame_index = frame_number % self._cycle_length
        y_offset = self._y_offset_for(state=state, frame_index=frame_index)
        return AnimationFrame(
            state=state,
            frame_index=frame_index,
            y_offset=y_offset,
        )

    def _y_offset_for(
        self,
        state: AnimationState,
        frame_index: int,
    ) -> int:
        if state != AnimationState.IDLE:
            return 0

        if frame_index % self._idle_bob_period < self._idle_bob_period // 2:
            return self._idle_bob_offset

        return 0
