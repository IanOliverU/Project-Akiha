"""File-backed animation provider for sprite frame assets."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from project_akiha.core.state.animation import (
    AnimationClipId,
    AnimationSequenceId,
    AnimationState,
)
from project_akiha.providers.animation.base import AnimationFrame, AnimationSequence


class AnimationManifestError(ValueError):
    """Raised when an animation manifest cannot be loaded."""


@dataclass(frozen=True, slots=True)
class AnimationClip:
    """A sequence of image frames for one animation state."""

    state: AnimationState
    frame_paths: tuple[Path, ...]
    ticks_per_frame: int
    clip_id: AnimationClipId | None = None
    loop: bool = True
    interruptible: bool = True
    fallback_state: AnimationState = AnimationState.IDLE
    x_offset: int = 0
    y_offset: int = 0
    scale_percent: int = 100
    source_rects: tuple[tuple[int, int, int, int] | None, ...] = ()
    frame_offsets: tuple[tuple[int, int], ...] = ()
    frame_durations: tuple[int, ...] = ()

    @property
    def duration_ticks(self) -> int:
        """Return one complete logical pass through the clip."""
        if self.frame_durations:
            return sum(self.frame_durations)
        return len(self.frame_paths) * self.ticks_per_frame

    def frame_for(self, frame_number: int) -> AnimationFrame:
        """Return the frame represented by the global clock tick."""
        frame_index = self._frame_index(frame_number)
        source_rect = self.source_rects[frame_index] if self.source_rects else None
        frame_x_offset, frame_y_offset = (
            self.frame_offsets[frame_index] if self.frame_offsets else (0, 0)
        )
        source_x, source_y, source_width, source_height = source_rect or (
            0,
            0,
            None,
            None,
        )
        return AnimationFrame(
            state=self.state,
            frame_index=frame_index,
            x_offset=self.x_offset + frame_x_offset,
            y_offset=self.y_offset + frame_y_offset,
            scale_percent=self.scale_percent,
            image_path=self.frame_paths[frame_index],
            source_x=source_x,
            source_y=source_y,
            source_width=source_width,
            source_height=source_height,
        )

    def _frame_index(self, frame_number: int) -> int:
        if not self.frame_durations:
            index = frame_number // self.ticks_per_frame
            if self.loop:
                return index % len(self.frame_paths)
            return min(index, len(self.frame_paths) - 1)

        cycle_duration = sum(self.frame_durations)
        if not self.loop and frame_number >= cycle_duration:
            return len(self.frame_paths) - 1
        cycle_tick = frame_number % cycle_duration
        elapsed_ticks = 0
        for frame_index, duration in enumerate(self.frame_durations):
            elapsed_ticks += duration
            if cycle_tick < elapsed_ticks:
                return frame_index
        raise AssertionError("Animation duration lookup exceeded its cycle.")


class AssetAnimationProvider:
    """Load animation frame paths from a TOML manifest."""

    def __init__(
        self,
        clips: dict[AnimationState, AnimationClip],
        *,
        named_clips: dict[AnimationClipId, AnimationClip] | None = None,
        sequences: dict[AnimationSequenceId, AnimationSequence] | None = None,
    ) -> None:
        if not clips:
            message = "Animation manifest must define at least one clip."
            raise AnimationManifestError(message)
        self._clips = clips
        self._named_clips = named_clips or {}
        self._sequences = sequences or {}
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
        named_clips = _parse_named_clips(
            manifest.get("clips"),
            manifest_path.parent,
        )
        sequences = _parse_sequences(
            manifest.get("sequences"),
            named_clips,
            clips,
        )
        return cls(clips=clips, named_clips=named_clips, sequences=sequences)

    def available_states(self) -> frozenset[AnimationState]:
        """Return animation states supported by this provider."""
        return frozenset(self._clips)

    def clip_for(self, state: AnimationState) -> AnimationClip:
        """Return an explicitly declared clip for validation and review tooling."""
        if not isinstance(state, AnimationState):
            raise TypeError("state must be an AnimationState value.")
        try:
            return self._clips[state]
        except KeyError as error:
            raise KeyError(
                f"Animation state is not declared: {state.value}."
            ) from error

    def clips_for_review(self) -> tuple[AnimationClip, ...]:
        """Return every legacy and staged clip for trusted asset validation."""
        return tuple(self._clips.values()) + tuple(self._named_clips.values())

    def available_sequences(self) -> frozenset[AnimationSequenceId]:
        """Return staged sequences supported by this appearance manifest."""
        return frozenset(self._sequences)

    def sequence_for(self, sequence_id: AnimationSequenceId) -> AnimationSequence:
        """Return one validated staged sequence."""
        if not isinstance(sequence_id, AnimationSequenceId):
            raise TypeError("sequence_id must be an AnimationSequenceId value.")
        try:
            return self._sequences[sequence_id]
        except KeyError as error:
            raise KeyError(
                f"Animation sequence is not declared: {sequence_id.value}."
            ) from error

    def frame_for_clip(
        self,
        clip_id: AnimationClipId,
        frame_number: int,
    ) -> AnimationFrame:
        """Return a frame from one validated staged clip."""
        return self._named_clip(clip_id).frame_for(frame_number)

    def clip_duration_ticks(self, clip_id: AnimationClipId) -> int:
        """Return one finite pass through a staged clip."""
        return self._named_clip(clip_id).duration_ticks

    def clip_loops(self, clip_id: AnimationClipId) -> bool:
        """Return whether a staged clip loops indefinitely."""
        return self._named_clip(clip_id).loop

    def _named_clip(self, clip_id: AnimationClipId) -> AnimationClip:
        if not isinstance(clip_id, AnimationClipId):
            raise TypeError("clip_id must be an AnimationClipId value.")
        try:
            return self._named_clips[clip_id]
        except KeyError as error:
            raise KeyError(
                f"Animation clip is not declared: {clip_id.value}."
            ) from error

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
    *,
    clip_id: AnimationClipId | None = None,
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

    frame_offsets = _parse_frame_offsets(
        state_name=state_name,
        value=state_data.get("frame_offsets"),
        frame_count=len(frame_paths),
    )
    frame_durations = _parse_frame_durations(
        state_name=state_name,
        value=state_data.get("frame_durations"),
        frame_count=len(frame_paths),
    )

    loop = state_data.get("loop", True)
    if type(loop) is not bool:
        raise AnimationManifestError(f"Animation {state_name} loop must be a boolean.")
    interruptible = state_data.get("interruptible", True)
    if type(interruptible) is not bool:
        raise AnimationManifestError(
            f"Animation {state_name} interruptible must be a boolean."
        )
    fallback_state = _parse_optional_state(
        state_data.get("fallback_state", AnimationState.IDLE.value),
        f"Animation {state_name} fallback_state",
    )

    return AnimationClip(
        state=_parse_state(state_name),
        frame_paths=frame_paths,
        ticks_per_frame=ticks_per_frame,
        clip_id=clip_id,
        loop=loop,
        interruptible=interruptible,
        fallback_state=fallback_state,
        x_offset=x_offset,
        y_offset=y_offset,
        scale_percent=scale_percent,
        source_rects=source_rects,
        frame_offsets=frame_offsets,
        frame_durations=frame_durations,
    )


def _parse_named_clips(
    value: Any,
    manifest_dir: Path,
) -> dict[AnimationClipId, AnimationClip]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise AnimationManifestError("Manifest [clips] must be a table.")

    clips: dict[AnimationClipId, AnimationClip] = {}
    for clip_name, clip_data in value.items():
        try:
            clip_id = AnimationClipId(clip_name)
        except ValueError as error:
            raise AnimationManifestError(
                f"Unknown staged animation clip: {clip_name}."
            ) from error
        if not isinstance(clip_data, dict):
            raise AnimationManifestError(f"Animation clip {clip_name} must be a table.")
        state_value = clip_data.get("state")
        state = _parse_optional_state(state_value, f"Animation clip {clip_name} state")
        clips[clip_id] = _parse_clip(
            state_name=state.value,
            state_data=clip_data,
            manifest_dir=manifest_dir,
            clip_id=clip_id,
        )
    return clips


def _parse_sequences(
    value: Any,
    named_clips: dict[AnimationClipId, AnimationClip],
    state_clips: dict[AnimationState, AnimationClip],
) -> dict[AnimationSequenceId, AnimationSequence]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise AnimationManifestError("Manifest [sequences] must be a table.")

    expected_states = {
        AnimationSequenceId.SLEEP: AnimationState.SLEEPING,
        AnimationSequenceId.WAKE: AnimationState.WAKING,
    }
    sequences: dict[AnimationSequenceId, AnimationSequence] = {}
    for sequence_name, sequence_data in value.items():
        try:
            sequence_id = AnimationSequenceId(sequence_name)
        except ValueError as error:
            raise AnimationManifestError(
                f"Unknown animation sequence: {sequence_name}."
            ) from error
        if not isinstance(sequence_data, dict):
            raise AnimationManifestError(
                f"Animation sequence {sequence_name} must be a table."
            )
        state = _parse_optional_state(
            sequence_data.get("state"),
            f"Animation sequence {sequence_name} state",
        )
        if state is not expected_states[sequence_id]:
            raise AnimationManifestError(
                f"Animation sequence {sequence_name} has an incompatible state."
            )
        clip_values = sequence_data.get("clips")
        if not isinstance(clip_values, list) or not clip_values:
            raise AnimationManifestError(
                f"Animation sequence {sequence_name} requires clips."
            )
        try:
            clip_ids = tuple(AnimationClipId(item) for item in clip_values)
        except (TypeError, ValueError) as error:
            raise AnimationManifestError(
                f"Animation sequence {sequence_name} contains an unknown clip."
            ) from error
        if len(set(clip_ids)) != len(clip_ids):
            raise AnimationManifestError(
                f"Animation sequence {sequence_name} repeats a clip."
            )
        for index, clip_id in enumerate(clip_ids):
            clip = named_clips.get(clip_id)
            if clip is None:
                raise AnimationManifestError(
                    f"Animation sequence {sequence_name} references missing clip "
                    f"{clip_id.value}."
                )
            if clip.state is not state:
                raise AnimationManifestError(
                    f"Animation sequence {sequence_name} clip {clip_id.value} "
                    "has an incompatible state."
                )
            if not clip.interruptible:
                raise AnimationManifestError(
                    f"Animation sequence {sequence_name} clip {clip_id.value} "
                    "must remain interruptible."
                )
            if clip.loop and index != len(clip_ids) - 1:
                raise AnimationManifestError(
                    f"Animation sequence {sequence_name} can loop only on its "
                    "final clip."
                )
        final_clip = named_clips[clip_ids[-1]]
        if sequence_id is AnimationSequenceId.SLEEP and not final_clip.loop:
            raise AnimationManifestError(
                "Animation sequence sleep must end with a looping clip."
            )
        if sequence_id is AnimationSequenceId.WAKE and final_clip.loop:
            raise AnimationManifestError(
                "Animation sequence wake must end with a one-shot clip."
            )
        interruptible = sequence_data.get("interruptible", True)
        if type(interruptible) is not bool:
            raise AnimationManifestError(
                f"Animation sequence {sequence_name} interruptible must be a boolean."
            )
        if (
            sequence_id in {AnimationSequenceId.SLEEP, AnimationSequenceId.WAKE}
            and not interruptible
        ):
            raise AnimationManifestError(
                f"Animation sequence {sequence_name} must remain interruptible."
            )
        fallback_state = _parse_optional_state(
            sequence_data.get("fallback_state", AnimationState.IDLE.value),
            f"Animation sequence {sequence_name} fallback_state",
        )
        if fallback_state not in state_clips:
            raise AnimationManifestError(
                f"Animation sequence {sequence_name} fallback_state is unavailable."
            )
        sequences[sequence_id] = AnimationSequence(
            sequence_id=sequence_id,
            state=state,
            clip_ids=clip_ids,
            fallback_state=fallback_state,
            interruptible=interruptible,
        )
    return sequences


def _parse_optional_state(value: Any, label: str) -> AnimationState:
    if not isinstance(value, str):
        raise AnimationManifestError(f"{label} must be a known animation state.")
    try:
        return AnimationState(value)
    except ValueError as error:
        raise AnimationManifestError(
            f"{label} must be a known animation state."
        ) from error


def _parse_frame_offsets(
    *,
    state_name: str,
    value: Any,
    frame_count: int,
) -> tuple[tuple[int, int], ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or len(value) != frame_count:
        raise AnimationManifestError(
            f"Animation {state_name} frame_offsets must match its frame count."
        )

    offsets: list[tuple[int, int]] = []
    for offset in value:
        if (
            not isinstance(offset, list)
            or len(offset) != 2
            or any(type(component) is not int for component in offset)
        ):
            message = (
                f"Animation {state_name} frame_offsets must contain "
                "integer [x, y] pairs."
            )
            raise AnimationManifestError(message)
        offsets.append((offset[0], offset[1]))
    return tuple(offsets)


def _parse_frame_durations(
    *,
    state_name: str,
    value: Any,
    frame_count: int,
) -> tuple[int, ...]:
    if value is None:
        return ()
    if (
        not isinstance(value, list)
        or len(value) != frame_count
        or any(type(duration) is not int or duration <= 0 for duration in value)
    ):
        raise AnimationManifestError(
            f"Animation {state_name} frame_durations must contain one "
            "positive integer per frame."
        )
    return tuple(value)


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

    frame_paths = tuple(
        _resolve_image_path(manifest_dir, frame, state_name) for frame in frames
    )
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
    image_path = _resolve_image_path(manifest_dir, filmstrip, state_name)
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


def _resolve_image_path(manifest_dir: Path, value: str, state_name: str) -> Path:
    if "\\" in value or ":" in value:
        raise AnimationManifestError(
            f"Animation {state_name} image paths must be normalized relative PNG paths."
        )
    relative = PurePosixPath(value)
    if (
        relative.is_absolute()
        or relative.as_posix() != value
        or any(part in {"", ".", ".."} for part in relative.parts)
        or relative.suffix.lower() != ".png"
    ):
        raise AnimationManifestError(
            f"Animation {state_name} image paths must be normalized relative PNG paths."
        )
    root = manifest_dir.resolve()
    candidate = manifest_dir / Path(*relative.parts)
    resolved = candidate.resolve()
    if resolved == root or root not in resolved.parents:
        raise AnimationManifestError(
            f"Animation {state_name} image path escaped the manifest directory."
        )
    return candidate
