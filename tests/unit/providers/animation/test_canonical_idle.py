"""Contract tests for Akiha's canonical-source idle animation."""

from __future__ import annotations

import hashlib
import tomllib
import unittest
from pathlib import Path

from PIL import Image

from project_akiha.core.state.animation import AnimationState
from project_akiha.providers.animation import AssetAnimationProvider

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_CANONICAL_PATH = _PROJECT_ROOT / "assets/animations/akiha/standing/000.png"
_MANIFEST_PATH = _PROJECT_ROOT / "assets/animations/manifest.toml"
_EXPERIMENT_MANIFEST_PATH = (
    _PROJECT_ROOT / "assets/animations/manifest.idle-60fps-experiment.toml"
)
_CANONICAL_SHA256 = "b74a30f8a198658a09478d12b98fe66cc075ab775bb7d7239b65bb5676c4cf81"
_EXPECTED_OFFSETS = (
    (0, 0),
    (0, 0),
    (0, 0),
    (0, 0),
    (0, -1),
    (0, -1),
    (0, -1),
    (0, -1),
    (0, -2),
    (0, -2),
    (0, -2),
    (0, -1),
    (0, -1),
    (0, -1),
    (0, 0),
    (0, 0),
)


class CanonicalIdleContractTest(unittest.TestCase):
    """Ensure idle motion cannot reinterpret the authoritative sprite."""

    def test_canonical_sprite_dimensions_palette_alpha_and_fingerprint(self) -> None:
        image = Image.open(_CANONICAL_PATH).convert("RGBA")
        pixels = tuple(image.get_flattened_data())

        self.assertEqual(image.size, (100, 100))
        self.assertEqual({alpha for *_, alpha in pixels}, {0, 255})
        self.assertEqual(
            len({(red, green, blue) for red, green, blue, alpha in pixels if alpha}),
            27,
        )
        self.assertEqual(
            hashlib.sha256(_CANONICAL_PATH.read_bytes()).hexdigest(),
            _CANONICAL_SHA256,
        )

    def test_every_idle_pose_uses_only_the_canonical_image(self) -> None:
        provider = AssetAnimationProvider.from_manifest(_MANIFEST_PATH)

        frames = tuple(
            provider.frame_for(AnimationState.IDLE, frame_number=index * 3)
            for index in range(len(_EXPECTED_OFFSETS))
        )

        self.assertEqual(
            tuple((frame.x_offset, frame.y_offset) for frame in frames),
            _EXPECTED_OFFSETS,
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
        self.assertTrue(all(frame.image_path == _CANONICAL_PATH for frame in frames))
        self.assertTrue(all(frame.scale_percent == 100 for frame in frames))
        self.assertEqual(
            {(frame.x_offset, frame.y_offset) for frame in frames},
            {(0, 0), (0, -1), (0, -2)},
        )
        self.assertEqual(loop_start.frame_index, frames[0].frame_index)
        self.assertEqual(loop_start.image_path, _CANONICAL_PATH)


if __name__ == "__main__":
    unittest.main()
