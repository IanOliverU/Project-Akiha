"""Tests for the read-only Akiha Status window."""

from __future__ import annotations

import os
import sys
import unittest
from datetime import UTC, datetime

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from project_akiha.core.appearance import AppearanceId
from project_akiha.core.behavior import ActivityState, CompanionMood
from project_akiha.core.pet import PetState, PetStateRecord
from project_akiha.core.pet_activity import PetActivityId
from project_akiha.core.state.animation import AnimationState
from project_akiha.services.pet_diagnostics import build_pet_diagnostics
from project_akiha.services.pet_status import (
    PetRuntimeStatus,
    PetStatusSnapshot,
    PetSystemDiagnostics,
)
from project_akiha.ui.pet_status_window import PetStatusWindow


class PetStatusWindowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication(sys.argv)

    def tearDown(self) -> None:
        if hasattr(self, "_window"):
            self._window.close()

    def test_renders_status_without_mutation_controls(self) -> None:
        self._window = PetStatusWindow()
        now = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
        snapshot = PetStatusSnapshot(
            pet=build_pet_diagnostics(
                PetStateRecord(
                    PetState.initial(),
                    revision=0,
                    evaluated_at=now,
                    created_at=now,
                    updated_at=now,
                )
            ),
            runtime=PetRuntimeStatus(
                mood=CompanionMood.CALM,
                user_activity=ActivityState.IDLE,
                animation_state=AnimationState.IDLE,
                autonomous_activity_id=PetActivityId.QUIET_IDLE,
            ),
            systems=PetSystemDiagnostics(
                catalog_version=2,
                catalog_item_count=0,
                available_catalog_item_count=0,
                catalog_failure=None,
                owned_item_count=0,
                transaction_count=0,
                last_purchase_at=None,
                appearance_count=3,
                available_appearance_count=1,
                owned_appearance_count=1,
                current_appearance_id=AppearanceId.SEIFUKU,
                activity_definition_count=3,
                active_activity_id=PetActivityId.QUIET_IDLE,
            ),
        )

        self._window.update_snapshot(snapshot)

        self.assertEqual(
            self._window._summary_label.text(),
            "Akiha could use some attention",
        )
        self.assertEqual(self._window._runtime_values["appearance"].text(), "seifuku")
        self.assertIn("no payments", self._window._diagnostic_values["privacy"].text())
        button_texts = {
            button.text()
            for button in self._window.findChildren(type(self._window._refresh_button))
        }
        self.assertNotIn("Reset", button_texts)
        self.assertNotIn("Purchase", button_texts)


if __name__ == "__main__":
    unittest.main()
