"""Contract tests for Akiha's canonical-source idle animation."""

from __future__ import annotations

import hashlib
import tomllib
import unittest
from pathlib import Path

from PIL import Image

from project_akiha.core.state.animation import (
    AnimationClipId,
    AnimationSequenceId,
    AnimationState,
)
from project_akiha.providers.animation import AssetAnimationProvider

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_CANONICAL_PATH = _PROJECT_ROOT / "assets/animations/akiha/seifuku-256/base.png"
_LEGACY_CANONICAL_PATH = _PROJECT_ROOT / "assets/animations/akiha/standing/000.png"
_MANIFEST_PATH = _PROJECT_ROOT / "assets/animations/manifest.toml"
_EXPERIMENT_MANIFEST_PATH = (
    _PROJECT_ROOT / "assets/animations/manifest.idle-60fps-experiment.toml"
)
_CANONICAL_SHA256 = "0082d8d17df60cdda252fed6437ef1e5988366d740f420eb17b95c55d9a2c00b"


class CanonicalIdleContractTest(unittest.TestCase):
    """Ensure idle motion cannot reinterpret the authoritative sprite."""

    def test_canonical_sprite_dimensions_alpha_and_fingerprint(self) -> None:
        image = Image.open(_CANONICAL_PATH).convert("RGBA")
        pixels = tuple(image.get_flattened_data())

        self.assertEqual(image.size, (256, 256))
        alpha_values = {alpha for *_, alpha in pixels}
        self.assertIn(0, alpha_values)
        self.assertIn(255, alpha_values)
        self.assertEqual(
            hashlib.sha256(_CANONICAL_PATH.read_bytes()).hexdigest(),
            _CANONICAL_SHA256,
        )

    def test_every_idle_pose_uses_only_the_canonical_image(self) -> None:
        provider = AssetAnimationProvider.from_manifest(_MANIFEST_PATH)

        frames = tuple(
            provider.frame_for(AnimationState.IDLE, index) for index in range(16)
        )

        self.assertEqual(
            {(frame.x_offset, frame.y_offset) for frame in frames}, {(0, 0)}
        )
        self.assertTrue(all(frame.image_path == _CANONICAL_PATH for frame in frames))
        self.assertTrue(all(frame.scale_percent == 100 for frame in frames))
        self.assertTrue(all(frame.source_width is None for frame in frames))

    def test_experimental_timeline_is_canonical_600_ticks_at_60_fps(self) -> None:
        manifest = tomllib.loads(_EXPERIMENT_MANIFEST_PATH.read_text("utf-8"))
        experiment = manifest["experiment"]
        durations = manifest["animations"]["idle"]["frame_durations"]
        provider = AssetAnimationProvider.from_manifest(_EXPERIMENT_MANIFEST_PATH)

        frames = tuple(
            provider.frame_for(AnimationState.IDLE, frame_number=tick)
            for tick in range(600)
        )
        loop_start = provider.frame_for(AnimationState.IDLE, frame_number=600)

        self.assertEqual(experiment["required_frames_per_second"], 60)
        self.assertEqual(experiment["cycle_ticks"], 600)
        self.assertEqual(sum(durations), 600)
        self.assertEqual(600 / 60, 10)
        self.assertTrue(
            all(frame.image_path == _LEGACY_CANONICAL_PATH for frame in frames)
        )
        self.assertTrue(all(frame.scale_percent == 100 for frame in frames))
        self.assertEqual(
            {(frame.x_offset, frame.y_offset) for frame in frames},
            {(0, 0), (0, -1), (0, -2)},
        )
        self.assertEqual(loop_start.frame_index, frames[0].frame_index)
        self.assertEqual(loop_start.image_path, _LEGACY_CANONICAL_PATH)

    def test_active_manifest_exposes_staged_sleep_and_wake_sequences(self) -> None:
        provider = AssetAnimationProvider.from_manifest(_MANIFEST_PATH)

        self.assertEqual(
            provider.available_sequences(),
            frozenset({AnimationSequenceId.SLEEP, AnimationSequenceId.WAKE}),
        )
        self.assertEqual(
            provider.sequence_for(AnimationSequenceId.SLEEP).clip_ids,
            (AnimationClipId.SLEEP_START, AnimationClipId.SLEEP_LOOP),
        )
        self.assertEqual(
            provider.sequence_for(AnimationSequenceId.WAKE).clip_ids,
            (AnimationClipId.WAKE_START,),
        )
        self.assertEqual(provider.clip_duration_ticks(AnimationClipId.SLEEP_START), 288)
        self.assertEqual(provider.clip_duration_ticks(AnimationClipId.SLEEP_LOOP), 180)
        self.assertEqual(provider.clip_duration_ticks(AnimationClipId.WAKE_START), 216)
        self.assertTrue(provider.clip_loops(AnimationClipId.SLEEP_LOOP))


if __name__ == "__main__":
    unittest.main()
