"""Tests for strict autonomous activity manifest loading."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from project_akiha.core.pet_activity import (
    PetActivityId,
    PetActivityManifestError,
    load_pet_activity_manifest,
)
from project_akiha.core.state.animation import AnimationState


class PetActivityManifestTest(unittest.TestCase):
    def test_bundled_manifest_defines_closed_approved_activities(self) -> None:
        definitions = load_pet_activity_manifest(
            Path("assets/animations/activities.toml")
        )

        self.assertEqual(
            {value.activity_id for value in definitions},
            set(PetActivityId),
        )
        self.assertEqual(
            {value.activity_id: value.animation_state for value in definitions},
            {
                PetActivityId.QUIET_IDLE: AnimationState.IDLE,
                PetActivityId.WANDER: AnimationState.WALKING,
                PetActivityId.REST: AnimationState.SLEEPING,
            },
        )

    def test_rejects_incomplete_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "activities.toml"
            path.write_text(
                "schema_version = 1\nactivities = []\n",
                encoding="utf-8",
            )

            with self.assertRaises(PetActivityManifestError):
                load_pet_activity_manifest(path)

    def test_rejects_activity_mapped_to_unapproved_animation(self) -> None:
        source = Path("assets/animations/activities.toml").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "activities.toml"
            path.write_text(
                source.replace(
                    'id = "wander"\nanimation_state = "walking"',
                    'id = "wander"\nanimation_state = "dragging"',
                ),
                encoding="utf-8",
            )

            with self.assertRaises(PetActivityManifestError):
                load_pet_activity_manifest(path)


if __name__ == "__main__":
    unittest.main()
