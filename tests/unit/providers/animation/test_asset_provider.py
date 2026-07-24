"""Tests for the file-backed animation provider."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from project_akiha.core.state.animation import AnimationState
from project_akiha.providers.animation import (
    AnimationManifestError,
    AssetAnimationProvider,
)


class AssetAnimationProviderTest(unittest.TestCase):
    """Verify animation manifests are parsed into frame data."""

    def test_loads_manifest_and_resolves_relative_frame_paths(self) -> None:
        with TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "manifest.toml"
            manifest_path.write_text(
                "[animations.idle]\n"
                'frames = ["idle/000.png", "idle/001.png"]\n'
                "ticks_per_frame = 3\n"
                "y_offset = 2\n",
                encoding="utf-8",
            )

            provider = AssetAnimationProvider.from_manifest(manifest_path)
            frame = provider.frame_for(AnimationState.IDLE, frame_number=3)

        self.assertEqual(provider.available_states(), frozenset({AnimationState.IDLE}))
        self.assertEqual(frame.state, AnimationState.IDLE)
        self.assertEqual(frame.frame_index, 1)
        self.assertEqual(frame.y_offset, 2)
        self.assertEqual(frame.image_path, manifest_path.parent / "idle" / "001.png")

    def test_falls_back_to_idle_for_missing_state(self) -> None:
        with TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "manifest.toml"
            manifest_path.write_text(
                "[animations.idle]\n"
                'frames = ["idle/000.png"]\n'
                "ticks_per_frame = 1\n",
                encoding="utf-8",
            )

            provider = AssetAnimationProvider.from_manifest(manifest_path)
            frame = provider.frame_for(AnimationState.DRAGGING, frame_number=0)

        self.assertEqual(frame.state, AnimationState.IDLE)

    def test_loads_filmstrip_animation_frames(self) -> None:
        with TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "manifest.toml"
            manifest_path.write_text(
                "[animations.walking]\n"
                'filmstrip = "walking/walk.png"\n'
                "frame_width = 256\n"
                "frame_height = 128\n"
                "frame_count = 3\n"
                "ticks_per_frame = 2\n",
                encoding="utf-8",
            )

            provider = AssetAnimationProvider.from_manifest(manifest_path)
            frame = provider.frame_for(AnimationState.WALKING, frame_number=4)

        self.assertEqual(frame.state, AnimationState.WALKING)
        self.assertEqual(frame.frame_index, 2)
        self.assertEqual(
            frame.image_path, manifest_path.parent / "walking" / "walk.png"
        )
        self.assertEqual(frame.source_x, 512)
        self.assertEqual(frame.source_y, 0)
        self.assertEqual(frame.source_width, 256)
        self.assertEqual(frame.source_height, 128)

    def test_rejects_unknown_state(self) -> None:
        with TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "manifest.toml"
            manifest_path.write_text(
                "[animations.dancing]\n" 'frames = ["dancing/000.png"]\n',
                encoding="utf-8",
            )

            with self.assertRaises(AnimationManifestError):
                AssetAnimationProvider.from_manifest(manifest_path)

    def test_rejects_clip_with_both_frames_and_filmstrip(self) -> None:
        with TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "manifest.toml"
            manifest_path.write_text(
                "[animations.idle]\n"
                'frames = ["idle/000.png"]\n'
                'filmstrip = "idle/strip.png"\n'
                "frame_width = 1\n"
                "frame_height = 1\n"
                "frame_count = 1\n",
                encoding="utf-8",
            )

            with self.assertRaises(AnimationManifestError):
                AssetAnimationProvider.from_manifest(manifest_path)

    def test_rejects_filmstrip_without_positive_dimensions(self) -> None:
        with TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "manifest.toml"
            manifest_path.write_text(
                "[animations.walking]\n"
                'filmstrip = "walking/walk.png"\n'
                "frame_width = 0\n"
                "frame_height = 128\n"
                "frame_count = 3\n",
                encoding="utf-8",
            )

            with self.assertRaises(AnimationManifestError):
                AssetAnimationProvider.from_manifest(manifest_path)

    def test_rejects_empty_frames(self) -> None:
        with TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "manifest.toml"
            manifest_path.write_text(
                "[animations.idle]\n" "frames = []\n",
                encoding="utf-8",
            )

            with self.assertRaises(AnimationManifestError):
                AssetAnimationProvider.from_manifest(manifest_path)


if __name__ == "__main__":
    unittest.main()
