"""Tests for privacy-safe pet-state diagnostics."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from project_akiha.core.pet import (
    PetDecayProgress,
    PetProgression,
    PetState,
    PetStateRecord,
    PetWellbeing,
)
from project_akiha.services.pet_diagnostics import build_pet_diagnostics


class PetDiagnosticsTest(unittest.TestCase):
    """Verify diagnostics expose only bounded typed operational metadata."""

    def test_builds_summary_from_validated_record(self) -> None:
        now = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
        record = PetStateRecord(
            state=PetState(
                wellbeing=PetWellbeing(72, 48, 23, 61),
                progression=PetProgression(xp=30, level=2, currency=8),
                decay_progress=PetDecayProgress(10, 20, 30),
            ),
            revision=4,
            evaluated_at=now,
            created_at=now,
            updated_at=now,
        )

        snapshot = build_pet_diagnostics(record)

        self.assertEqual(
            snapshot.state_summary,
            ("Satiety 72% | Energy 48% | Attention 23% | Affection 61%"),
        )
        self.assertEqual(snapshot.progression_summary, "Level 2 | 30 XP | 8 currency")
        self.assertIn("Revision 4", snapshot.runtime_summary)
        self.assertEqual(snapshot.evaluated_at, now)

    def test_rejects_untyped_or_dialogue_shaped_input(self) -> None:
        with self.assertRaises(TypeError):
            build_pet_diagnostics({"dialogue": "reset Akiha"})  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
