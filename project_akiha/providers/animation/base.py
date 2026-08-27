"""Framework-free animation provider contract."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from project_akiha.core.state.animation import (
    AnimationClipId,
    AnimationSequenceId,
    AnimationState,
)


@dataclass(frozen=True, slots=True)
class AnimationFrame:
    """A renderable animation frame description."""

    state: AnimationState
    frame_index: int
    x_offset: int = 0
    y_offset: int = 0
    scale_percent: int = 100
    image_path: Path | None = None
    source_x: int = 0
    source_y: int = 0
    source_width: int | None = None
    source_height: int | None = None
    mirrored_horizontally: bool = False


@dataclass(frozen=True, slots=True)
class AnimationSequence:
    """Trusted ordered clips for one staged presentation sequence."""

    sequence_id: AnimationSequenceId
    state: AnimationState
    clip_ids: tuple[AnimationClipId, ...]
    fallback_state: AnimationState
    interruptible: bool

    def __post_init__(self) -> None:
        if not self.clip_ids:
            raise ValueError("animation sequence must contain at least one clip.")


class AnimationProvider(Protocol):
    """Provide animation frame data for a requested pet state."""

    def available_states(self) -> frozenset[AnimationState]:
        """Return animation states supported by this provider."""

    def frame_for(
        self,
        state: AnimationState,
        frame_number: int,
    ) -> AnimationFrame:
        """Return frame data for the given state and clock frame."""


@runtime_checkable
class SequenceAnimationProvider(AnimationProvider, Protocol):
    """Optional staged-playback extension for trusted animation providers."""

    def available_sequences(self) -> frozenset[AnimationSequenceId]:
        """Return staged sequences supported by the current appearance."""

    def sequence_for(self, sequence_id: AnimationSequenceId) -> AnimationSequence:
        """Return one validated staged sequence."""

    def frame_for_clip(
        self,
        clip_id: AnimationClipId,
        frame_number: int,
    ) -> AnimationFrame:
        """Return a frame from one validated named clip."""

    def clip_duration_ticks(self, clip_id: AnimationClipId) -> int:
        """Return the finite duration of one named clip in renderer ticks."""

    def clip_loops(self, clip_id: AnimationClipId) -> bool:
        """Return whether one named clip loops indefinitely."""
