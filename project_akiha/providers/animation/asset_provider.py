"""File-backed animation provider for sprite frame assets."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from project_akiha.core.state.animation import AnimationState
from project_akiha.providers.animation.base import AnimationFrame


class AnimationManifestError(ValueError):
    """Raised when an animation manifest cannot be loaded."""


@dataclass(frozen=True, slots=True)
class AnimationClip:
    """A sequence of image frames for one animation state."""

    state: AnimationState
    frame_paths: tuple[Path, ...]
    ticks_per_frame: int
    y_offset: int = 0

    def frame_for(self, frame_number: int) -> AnimationFrame:
        """Return the frame represented by the global clock tick."""
        frame_index = (frame_number // self.ticks_per_frame) % len(self.frame_paths)
        return AnimationFrame(
            state=self.state,
            frame_index=frame_index,
            y_offset=self.y_offset,
            image_path=self.frame_paths[frame_index],
        )


class AssetAnimationProvider:
    """Load animation frame paths from a TOML manifest."""

    def __init__(self, clips: dict[AnimationState, AnimationClip]) -> None:
        if not clips:
            message = "Animation manifest must define at least one clip."
            raise AnimationManifestError(message)
        self._clips = clips
        self._fallback_state = (
            AnimationState.IDLE if AnimationState.IDLE in clips else next(iter(clips))
        )

    @classmethod
    def from_manifest(cls, manifest_path: Path) -> AssetAnimationProvider:
        """Load an animation provider from a TOML manifest."""
        try:
            manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
        except OSError as error:
            raise AnimationManifestError(f"Unable to read {manifest_path}.") from error
        except tomllib.TOMLDecodeError as error:
            raise AnimationManifestError(f"Invalid TOML in {manifest_path}.") from error

        animations = manifest.get("animations")
        if not isinstance(animations, dict):
            raise AnimationManifestError("Manifest must include an [animations] table.")

        clips = {
            _parse_state(state_name): _parse_clip(
                state_name=state_name,
                state_data=state_data,
                manifest_dir=manifest_path.parent,
            )
            for state_name, state_data in animations.items()
        }
        return cls(clips=clips)

    def available_states(self) -> frozenset[AnimationState]:
        """Return animation states supported by this provider."""
        return frozenset(self._clips)

    def frame_for(
        self,
        state: AnimationState,
        frame_number: int,
    ) -> AnimationFrame:
        """Return frame data for the requested state."""
        clip = self._clips.get(state) or self._clips[self._fallback_state]
        return clip.frame_for(frame_number)


def _parse_state(state_name: str) -> AnimationState:
    try:
        return AnimationState(state_name)
    except ValueError as error:
        message = f"Unknown animation state: {state_name}."
        raise AnimationManifestError(message) from error


def _parse_clip(
    state_name: str,
    state_data: Any,
    manifest_dir: Path,
) -> AnimationClip:
    if not isinstance(state_data, dict):
        raise AnimationManifestError(f"Animation {state_name} must be a table.")

    frames = state_data.get("frames")
    if not isinstance(frames, list) or not frames:
        raise AnimationManifestError(f"Animation {state_name} requires frames.")
    if not all(isinstance(frame, str) and frame for frame in frames):
        raise AnimationManifestError(f"Animation {state_name} frames must be strings.")

    ticks_per_frame = state_data.get("ticks_per_frame", 1)
    if type(ticks_per_frame) is not int or ticks_per_frame <= 0:
        raise AnimationManifestError(
            f"Animation {state_name} ticks_per_frame must be a positive integer."
        )

    y_offset = state_data.get("y_offset", 0)
    if type(y_offset) is not int:
        raise AnimationManifestError(
            f"Animation {state_name} y_offset must be an integer."
        )

    return AnimationClip(
        state=_parse_state(state_name),
        frame_paths=tuple(manifest_dir / frame for frame in frames),
        ticks_per_frame=ticks_per_frame,
        y_offset=y_offset,
    )
