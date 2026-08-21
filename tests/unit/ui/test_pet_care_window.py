"""Tests for the compact pet status and care surface."""

from __future__ import annotations

import os
import sys
import unittest
from datetime import UTC, datetime

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton

from project_akiha.core.pet import (
    CareAction,
    PetProgression,
    PetState,
    PetStateRecord,
    PetWellbeing,
)
from project_akiha.ui.pet_care_window import PetCareWindow


class PetCareWindowTest(unittest.TestCase):
    """Verify typed controls and deterministic state presentation."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication(sys.argv)

    def tearDown(self) -> None:
        if hasattr(self, "_window"):
            self._window.close()

    def test_renders_wellbeing_progression_and_summary(self) -> None:
        self._window = PetCareWindow()

        self._window.update_record(
            _record(
                wellbeing=PetWellbeing(
                    satiety=72,
                    energy=48,
                    attention=23,
                    affection=61,
                ),
                progression=PetProgression(xp=30, level=2, currency=8),
            )
        )

        self.assertEqual(self._window._need_values["satiety"].text(), "72%")
        self.assertEqual(self._window._need_bars["energy"].value(), 48)
        self.assertEqual(
            self._window._need_bars["energy"].property("semantic"),
            "low",
        )
        self.assertEqual(
            self._window._need_bars["attention"].property("semantic"),
            "critical",
        )
        self.assertEqual(self._window._level_label.text(), "Level 2")
        self.assertEqual(self._window._currency_label.text(), "8 currency")
        self.assertEqual(self._window._xp_label.text(), "5 / 50 XP")
        self.assertEqual(self._window._xp_bar.value(), 5)
        self.assertEqual(self._window._summary_label.text(), "Akiha needs care")

    def test_care_buttons_emit_only_closed_care_actions(self) -> None:
        self._window = PetCareWindow()
        emitted: list[CareAction] = []
        self._window.care_action_requested.connect(emitted.append)

        for button in self._window._care_buttons:
            button.click()

        self.assertEqual(
            emitted,
            [CareAction.FEED, CareAction.REST, CareAction.SPEND_TIME],
        )

    def test_shop_header_control_emits_open_request(self) -> None:
        self._window = PetCareWindow()
        emitted: list[bool] = []
        self._window.shop_requested.connect(lambda: emitted.append(True))

        shop_button = next(
            button
            for button in self._window.findChildren(QPushButton)
            if button.toolTip() == "Open shop and wardrobe"
        )
        shop_button.click()

        self.assertEqual(emitted, [True])

    def test_busy_state_blocks_refresh_and_care_controls(self) -> None:
        self._window = PetCareWindow()

        self._window.set_busy(True)

        self.assertFalse(self._window._refresh_button.isEnabled())
        self.assertTrue(
            all(not button.isEnabled() for button in self._window._care_buttons)
        )
        self.assertIn("Updating", self._window._notice_label.text())

        self._window.set_busy(False)

        self.assertTrue(self._window._refresh_button.isEnabled())
        self.assertTrue(
            all(button.isEnabled() for button in self._window._care_buttons)
        )

    def test_rejects_untyped_records(self) -> None:
        self._window = PetCareWindow()

        with self.assertRaises(TypeError):
            self._window.update_record({"satiety": 100})  # type: ignore[arg-type]


def _record(
    *,
    wellbeing: PetWellbeing,
    progression: PetProgression,
) -> PetStateRecord:
    now = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
    return PetStateRecord(
        state=PetState(wellbeing=wellbeing, progression=progression),
        revision=3,
        evaluated_at=now,
        created_at=now,
        updated_at=now,
    )


if __name__ == "__main__":
    unittest.main()
