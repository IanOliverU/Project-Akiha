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
    x_offset: int = 0
    y_offset: int = 0
    scale_percent: int = 100
    source_rects: tuple[tuple[int, int, int, int] | None, ...] = ()

    def frame_for(self, frame_number: int) -> AnimationFrame:
        """Return the frame represented by the global clock tick."""
        frame_index = (frame_number // self.ticks_per_frame) % len(self.frame_paths)
        source_rect = self.source_rects[frame_index] if self.source_rects else None
        source_x, source_y, source_width, source_height = source_rect or (
            0,
            0,
            None,
            None,
        )
        return AnimationFrame(
            state=self.state,
            frame_index=frame_index,
            x_offset=self.x_offset,
            y_offset=self.y_offset,
            scale_percent=self.scale_percent,
            image_path=self.frame_paths[frame_index],
            source_x=source_x,
            source_y=source_y,
            source_width=source_width,
            source_height=source_height,
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

    frame_paths, source_rects = _parse_frame_sources(
        state_name=state_name,
        state_data=state_data,
        manifest_dir=manifest_dir,
    )

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

    x_offset = state_data.get("x_offset", 0)
    if type(x_offset) is not int:
        raise AnimationManifestError(
            f"Animation {state_name} x_offset must be an integer."
        )

    scale_percent = state_data.get("scale_percent", 100)
    if type(scale_percent) is not int or scale_percent <= 0:
        raise AnimationManifestError(
            f"Animation {state_name} scale_percent must be a positive integer."
        )

    return AnimationClip(
        state=_parse_state(state_name),
        frame_paths=frame_paths,
        ticks_per_frame=ticks_per_frame,
        x_offset=x_offset,
        y_offset=y_offset,
        scale_percent=scale_percent,
        source_rects=source_rects,
    )


def _parse_frame_sources(
    state_name: str,
    state_data: dict[str, Any],
    manifest_dir: Path,
) -> tuple[tuple[Path, ...], tuple[tuple[int, int, int, int] | None, ...]]:
    frames = state_data.get("frames")
    filmstrip = state_data.get("filmstrip")
    if frames is not None and filmstrip is not None:
        raise AnimationManifestError(
            f"Animation {state_name} cannot define both frames and filmstrip."
        )

    if filmstrip is not None:
        return _parse_filmstrip(state_name, state_data, manifest_dir)

    if not isinstance(frames, list) or not frames:
        raise AnimationManifestError(f"Animation {state_name} requires frames.")
    if not all(isinstance(frame, str) and frame for frame in frames):
        raise AnimationManifestError(f"Animation {state_name} frames must be strings.")

    frame_paths = tuple(manifest_dir / frame for frame in frames)
    _ensure_files_exist(frame_paths, state_name)
    return frame_paths, ()


def _parse_filmstrip(
    state_name: str,
    state_data: dict[str, Any],
    manifest_dir: Path,
) -> tuple[tuple[Path, ...], tuple[tuple[int, int, int, int] | None, ...]]:
    filmstrip = state_data.get("filmstrip")
    if not isinstance(filmstrip, str) or not filmstrip:
        raise AnimationManifestError(
            f"Animation {state_name} filmstrip must be a string."
        )

    frame_width = _positive_int(
        state_data.get("frame_width"), "frame_width", state_name
    )
    frame_height = _positive_int(
        state_data.get("frame_height"),
        "frame_height",
        state_name,
    )
    frame_count = _positive_int(
        state_data.get("frame_count"), "frame_count", state_name
    )
    image_path = manifest_dir / filmstrip
    _ensure_files_exist((image_path,), state_name)
    frame_paths = tuple(image_path for _ in range(frame_count))
    source_rects = tuple(
        (index * frame_width, 0, frame_width, frame_height)
        for index in range(frame_count)
    )
    return frame_paths, source_rects


def _positive_int(value: Any, field_name: str, state_name: str) -> int:
    if type(value) is not int or value <= 0:
        raise AnimationManifestError(
            f"Animation {state_name} {field_name} must be a positive integer."
        )
    return value


def _ensure_files_exist(paths: tuple[Path, ...], state_name: str) -> None:
    missing_paths = [path for path in paths if not path.is_file()]
    if missing_paths:
        missing = ", ".join(str(path) for path in missing_paths)
        raise AnimationManifestError(
            f"Animation {state_name} references missing image file(s): {missing}."
        )
