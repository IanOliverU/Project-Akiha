"""Tests for complete appearance image and approval validation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from project_akiha.core.appearance import AppearanceId, load_appearance_registry
from project_akiha.services.appearance_asset_validation import (
    AppearanceAssetIssueCode,
    validate_appearance_manifest,
    validate_registered_appearance,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_REGISTRY_PATH = _PROJECT_ROOT / "assets/animations/appearances.toml"


class AppearanceAssetValidationTest(unittest.TestCase):
    def test_approved_seifuku_set_is_activation_ready(self) -> None:
        registry = load_appearance_registry(_REGISTRY_PATH)

        report = validate_registered_appearance(registry, AppearanceId.SEIFUKU)

        self.assertTrue(report.technically_valid)
        self.assertTrue(report.approval_present)
        self.assertTrue(report.approval_matches)
        self.assertTrue(report.activation_ready)
        self.assertEqual(report.unique_asset_count, 2)
        self.assertEqual(report.declared_frame_count, 26)
        self.assertEqual(report.issues, ())

    def test_unavailable_appearance_stays_inactive(self) -> None:
        registry = load_appearance_registry(_REGISTRY_PATH)

        report = validate_registered_appearance(registry, AppearanceId.DRESS)

        self.assertFalse(report.activation_ready)
        self.assertEqual(
            report.issues[0].code,
            AppearanceAssetIssueCode.APPEARANCE_UNAVAILABLE,
        )

    def test_candidate_requires_all_states_and_owner_approval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _sprite(root / "idle.png")
            manifest = root / "manifest.toml"
            manifest.write_text(
                "[animations.idle]\n" 'frames = ["idle.png"]\n' "ticks_per_frame = 1\n",
                encoding="utf-8",
            )

            report = validate_appearance_manifest(AppearanceId.DRESS, manifest)

        self.assertFalse(report.technically_valid)
        self.assertFalse(report.activation_ready)
        codes = {issue.code for issue in report.issues}
        self.assertIn(AppearanceAssetIssueCode.MISSING_STATE, codes)
        self.assertIn(AppearanceAssetIssueCode.APPROVAL_MISSING, codes)

    def test_rejects_non_rgba_nonbinary_or_wrong_sized_frames(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            Image.new("RGB", (100, 100), (10, 20, 30)).save(root / "bad.png")
            manifest = root / "manifest.toml"
            clips = "".join(
                f'[animations.{state}]\nframes = ["bad.png"]\n'
                for state in ("idle", "walking", "dragging", "sleeping")
            )
            manifest.write_text(clips, encoding="utf-8")

            report = validate_appearance_manifest(AppearanceId.DRESS, manifest)

        self.assertFalse(report.technically_valid)
        self.assertIn(
            AppearanceAssetIssueCode.IMAGE_MODE_INVALID,
            {issue.code for issue in report.issues},
        )


def _sprite(path: Path) -> None:
    image = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    image.putpixel((50, 50), (10, 20, 30, 255))
    image.save(path)


if __name__ == "__main__":
    unittest.main()
