"""Tests for complete canonical appearance manifests."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from project_akiha.core.appearance import (
    AppearanceAvailability,
    AppearanceDefinition,
    AppearanceId,
    AppearanceRegistryError,
    load_appearance_registry,
)


class AppearanceRegistryTest(unittest.TestCase):
    def test_bundled_registry_has_fixed_canonical_ids(self) -> None:
        registry = load_appearance_registry(Path("assets/animations/appearances.toml"))

        self.assertIs(registry.default_appearance_id, AppearanceId.SEIFUKU)
        self.assertEqual(
            frozenset(item.appearance_id for item in registry.definitions),
            frozenset(AppearanceId),
        )
        self.assertTrue(registry.manifest_path(AppearanceId.SEIFUKU).is_file())  # type: ignore[union-attr]
        self.assertIsNone(registry.manifest_path(AppearanceId.DRESS))

    def test_default_appearance_cannot_require_purchase_or_be_unavailable(self) -> None:
        with self.assertRaises(ValueError):
            AppearanceDefinition(
                AppearanceId.SEIFUKU,
                "Akiha - Seifuku",
                AppearanceAvailability.UNAVAILABLE,
            )
        with self.assertRaises(ValueError):
            AppearanceDefinition(
                AppearanceId.SEIFUKU,
                "Akiha - Seifuku",
                AppearanceAvailability.AVAILABLE,
                "manifest.toml",
                "approval.toml",
                "appearance.seifuku",
            )

    def test_loader_rejects_missing_manifests_and_unknown_fields(self) -> None:
        text = Path("assets/animations/appearances.toml").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "appearances.toml"
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(AppearanceRegistryError):
                load_appearance_registry(path)
            path.write_text(text + "\nunknown = true\n", encoding="utf-8")
            with self.assertRaises(AppearanceRegistryError):
                load_appearance_registry(path)

    def test_loader_rejects_changes_after_owner_approval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory) / "animations"
            shutil.copytree(Path("assets/animations"), copied)
            canonical = copied / "akiha/standing/000.png"
            canonical.write_bytes(canonical.read_bytes() + b"changed")

            with self.assertRaisesRegex(AppearanceRegistryError, "hash changed"):
                load_appearance_registry(copied / "appearances.toml")


if __name__ == "__main__":
    unittest.main()
