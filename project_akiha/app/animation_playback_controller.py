"""Framework-free playback for optional trusted animation sequences."""

from __future__ import annotations

from dataclasses import dataclass

from project_akiha.core.state.animation import (
    AnimationClipId,
    AnimationSequenceId,
    AnimationState,
)
from project_akiha.providers.animation import (
    AnimationFrame,
    AnimationProvider,
    AnimationSequence,
    SequenceAnimationProvider,
)


@dataclass(frozen=True, slots=True)
class AnimationSequenceCompletion:
    """One typed terminal sequence completion reported to state authority."""

    sequence_id: AnimationSequenceId
    state: AnimationState
    fallback_state: AnimationState


class AnimationPlaybackController:
    """Advance trusted clips without owning semantic pet-state transitions."""

    _sequence_for_state = {
        AnimationState.SLEEPING: AnimationSequenceId.SLEEP,
        AnimationState.WAKING: AnimationSequenceId.WAKE,
    }

    def __init__(
        self,
        provider: AnimationProvider,
        *,
        initial_state: AnimationState = AnimationState.IDLE,
    ) -> None:
        self._provider = provider
        self._state = initial_state
        self._sequence: AnimationSequence | None = None
        self._sequence_index = 0
        self._frame_number = 0
        self._completion_reported = False
        self.start_state(initial_state)

    @property
    def state(self) -> AnimationState:
        """Return the semantic state requested by the application controller."""
        return self._state

    @property
    def frame_number(self) -> int:
        """Return the current state-relative renderer tick."""
        return self._frame_number

    @property
    def active_sequence_id(self) -> AnimationSequenceId | None:
        """Return the active optional sequence identifier."""
        return self._sequence.sequence_id if self._sequence is not None else None

    @property
    def active_clip_id(self) -> AnimationClipId | None:
        """Return the active named clip, if staged playback is available."""
        if self._sequence is None:
            return None
        return self._sequence.clip_ids[self._sequence_index]

    @property
    def staged_sleep_available(self) -> bool:
        """Return whether both sleep and wake sequences are complete."""
        provider = self._sequence_provider
        if provider is None:
            return False
        available = provider.available_sequences()
        return {
            AnimationSequenceId.SLEEP,
            AnimationSequenceId.WAKE,
        }.issubset(available)

    def set_provider(self, provider: AnimationProvider) -> None:
        """Replace appearance assets and restart the current presentation."""
        self._provider = provider
        self.start_state(self._state)

    def start_state(self, state: AnimationState) -> None:
        """Start one semantic state from its first trusted frame."""
        if not isinstance(state, AnimationState):
            raise TypeError("state must be an AnimationState value.")
        self._state = state
        self._sequence = self._resolve_sequence(state)
        self._sequence_index = 0
        self._frame_number = 0
        self._completion_reported = False

    def frame(self) -> AnimationFrame:
        """Return the current trusted frame or the provider's safe fallback."""
        provider = self._sequence_provider
        clip_id = self.active_clip_id
        if provider is not None and clip_id is not None:
            return provider.frame_for_clip(clip_id, self._frame_number)
        return self._provider.frame_for(self._state, self._frame_number)

    def advance_tick(self) -> AnimationSequenceCompletion | None:
        """Advance one renderer tick and report a terminal one-shot sequence."""
        self._frame_number += 1
        provider = self._sequence_provider
        sequence = self._sequence
        clip_id = self.active_clip_id
        if provider is None or sequence is None or clip_id is None:
            return None
        if provider.clip_loops(clip_id):
            return None
        if self._frame_number < provider.clip_duration_ticks(clip_id):
            return None
        if self._sequence_index + 1 < len(sequence.clip_ids):
            self._sequence_index += 1
            self._frame_number = 0
            return None
        self._frame_number = max(0, provider.clip_duration_ticks(clip_id) - 1)
        if self._completion_reported:
            return None
        self._completion_reported = True
        return AnimationSequenceCompletion(
            sequence_id=sequence.sequence_id,
            state=sequence.state,
            fallback_state=sequence.fallback_state,
        )

    @property
    def _sequence_provider(self) -> SequenceAnimationProvider | None:
        if isinstance(self._provider, SequenceAnimationProvider):
            return self._provider
        return None

    def _resolve_sequence(self, state: AnimationState) -> AnimationSequence | None:
        sequence_id = self._sequence_for_state.get(state)
        provider = self._sequence_provider
        if sequence_id is None or provider is None:
            return None
        if sequence_id not in provider.available_sequences():
            return None
        return provider.sequence_for(sequence_id)
