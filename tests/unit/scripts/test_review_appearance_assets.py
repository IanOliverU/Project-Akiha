"""Tests for production-path appearance review artifacts."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from project_akiha.core.appearance import AppearanceId, load_appearance_registry
from project_akiha.services.appearance_asset_validation import (
    validate_registered_appearance,
)
from scripts.review_appearance_assets import generate_review_artifacts

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_REGISTRY_PATH = _PROJECT_ROOT / "assets/animations/appearances.toml"
_CANONICAL_PATH = _PROJECT_ROOT / "assets/animations/akiha/standing/000.png"


class AppearanceReviewArtifactTest(unittest.TestCase):
    def test_generates_contact_sheet_gifs_report_without_mutating_source(self) -> None:
        registry = load_appearance_registry(_REGISTRY_PATH)
        report = validate_registered_appearance(registry, AppearanceId.SEIFUKU)
        before = hashlib.sha256(_CANONICAL_PATH.read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            outputs = generate_review_artifacts(
                appearance_id=AppearanceId.SEIFUKU,
                manifest_path=registry.manifest_path(AppearanceId.SEIFUKU),  # type: ignore[arg-type]
                output_dir=Path(directory),
                report=report,
            )
            with Image.open(Path(directory) / "contact-sheet.png") as contact:
                self.assertGreater(contact.width, 0)
            with Image.open(Path(directory) / "idle.gif") as idle:
                self.assertEqual(idle.size, (100, 100))
            self.assertTrue(all(path.is_file() for path in outputs))

        after = hashlib.sha256(_CANONICAL_PATH.read_bytes()).hexdigest()
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
