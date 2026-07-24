"""Framework-free animation provider contract."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from project_akiha.core.state.animation import AnimationState


@dataclass(frozen=True, slots=True)
class AnimationFrame:
    """A renderable animation frame description."""

    state: AnimationState
    frame_index: int
    y_offset: int = 0
    image_path: Path | None = None
    source_x: int = 0
    source_y: int = 0
    source_width: int | None = None
    source_height: int | None = None


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
