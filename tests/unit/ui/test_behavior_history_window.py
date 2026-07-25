"""Tests for the behavior history viewer window."""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

from project_akiha.core.behavior import BehaviorEvent
from project_akiha.ui.behavior_history_window import BehaviorHistoryWindow


class BehaviorHistoryWindowTest(unittest.TestCase):
    """Verify behavior history filtering and details rendering."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication(sys.argv)

    def test_updates_events_and_selects_latest_event(self) -> None:
        window = BehaviorHistoryWindow()

        window.update_events(
            (
                _event(2, "proactive.suggestion_delivered", {"channel": "tray"}),
                _event(1, "proactive.suggestion_ready", {"reason": "idle"}),
            )
        )

        self.assertEqual(window._event_list.count(), 2)
        self.assertEqual(window.selected_event_id(), 2)
        self.assertIn(
            "proactive.suggestion_delivered", window._details_input.toPlainText()
        )
        self.assertEqual(window._status_label.text(), "2 behavior events")

    def test_filters_events_by_payload_text(self) -> None:
        window = BehaviorHistoryWindow()
        window.update_events(
            (
                _event(1, "proactive.suggestion_ready", {"reason": "idle"}),
                _event(2, "proactive.suggestion_delivered", {"channel": "chat"}),
            )
        )

        window._filter_input.setText("chat")

        self.assertTrue(window._event_list.item(0).isHidden())
        self.assertFalse(window._event_list.item(1).isHidden())
        self.assertEqual(window._status_label.text(), "1 of 2 behavior events")
        self.assertEqual(window.selected_event_id(), 2)

    def test_filters_events_by_event_type(self) -> None:
        window = BehaviorHistoryWindow()
        window.update_events(
            (
                _event(1, "proactive.suggestion_ready", {"reason": "idle"}),
                _event(2, "proactive.suggestion_delivered", {"channel": "tray"}),
            )
        )

        window._event_type_filter_input.setCurrentText("proactive.suggestion_ready")

        self.assertFalse(window._event_list.item(0).isHidden())
        self.assertTrue(window._event_list.item(1).isHidden())
        self.assertEqual(
            window.selected_event_type_filter(), "proactive.suggestion_ready"
        )
        self.assertEqual(window._status_label.text(), "1 of 2 behavior events")

    def test_filters_events_by_kind(self) -> None:
        window = BehaviorHistoryWindow()
        window.update_events(
            (
                _event(1, "proactive.suggestion_ready", {}, kind="idle_check_in"),
                _event(2, "proactive.suggestion_ready", {}, kind="scheduled_check_in"),
            )
        )

        window._kind_filter_input.setCurrentText("scheduled_check_in")

        self.assertTrue(window._event_list.item(0).isHidden())
        self.assertFalse(window._event_list.item(1).isHidden())
        self.assertEqual(window.selected_kind_filter(), "scheduled_check_in")

    def test_update_events_preserves_available_filters(self) -> None:
        window = BehaviorHistoryWindow()
        window.update_events(
            (
                _event(1, "proactive.suggestion_ready", {}, kind="idle_check_in"),
                _event(2, "proactive.suggestion_delivered", {}, kind="idle_check_in"),
            )
        )
        window._event_type_filter_input.setCurrentText("proactive.suggestion_ready")
        window._kind_filter_input.setCurrentText("idle_check_in")

        window.update_events(
            (
                _event(3, "proactive.suggestion_ready", {}, kind="idle_check_in"),
                _event(4, "mood.state_changed", {}, kind=None),
            )
        )

        self.assertEqual(
            window.selected_event_type_filter(), "proactive.suggestion_ready"
        )
        self.assertEqual(window.selected_kind_filter(), "idle_check_in")
        self.assertFalse(window._event_list.item(0).isHidden())
        self.assertTrue(window._event_list.item(1).isHidden())

    def test_filter_clears_selection_when_no_events_match(self) -> None:
        window = BehaviorHistoryWindow()
        window.update_events((_event(1, "proactive.suggestion_ready", {}),))

        window._filter_input.setText("missing")

        self.assertTrue(window._event_list.item(0).isHidden())
        self.assertIsNone(window.selected_event_id())
        self.assertEqual(window._details_input.toPlainText(), "")

    def test_filter_can_select_first_visible_row(self) -> None:
        window = BehaviorHistoryWindow()
        window.update_events(
            (
                _event(1, "proactive.suggestion_ready", {"reason": "idle"}),
                _event(2, "proactive.suggestion_delivered", {"channel": "tray"}),
            )
        )
        window._event_list.setCurrentRow(1)

        window._filter_input.setText("idle")

        self.assertEqual(window.selected_event_id(), 1)

    def test_selected_event_returns_full_event(self) -> None:
        window = BehaviorHistoryWindow()
        window.update_events(
            (
                _event(1, "proactive.suggestion_ready", {"reason": "idle"}),
                _event(2, "proactive.suggestion_delivered", {"channel": "tray"}),
            )
        )

        window._event_list.setCurrentRow(1)

        selected = window.selected_event()
        self.assertIsNotNone(selected)
        self.assertEqual(selected.id, 2)
        self.assertEqual(selected.payload["channel"], "tray")

    def test_clear_matching_requires_a_dropdown_filter(self) -> None:
        window = BehaviorHistoryWindow()

        window._request_clear_matching()

        self.assertEqual(
            window._status_label.text(),
            "Choose an event type or kind filter first.",
        )

    def test_clear_matching_emits_selected_filters_after_confirmation(self) -> None:
        window = BehaviorHistoryWindow()
        emitted: list[tuple[str, str]] = []
        window.clear_matching_requested.connect(
            lambda event_type, kind: emitted.append((event_type, kind))
        )
        window.update_events(
            (
                _event(1, "proactive.suggestion_ready", {}, kind="idle_check_in"),
                _event(2, "proactive.suggestion_delivered", {}, kind="idle_check_in"),
            )
        )
        window._event_type_filter_input.setCurrentText("proactive.suggestion_ready")

        with patch.object(
            QMessageBox,
            "question",
            return_value=QMessageBox.StandardButton.Yes,
        ):
            window._request_clear_matching()

        self.assertEqual(emitted, [("proactive.suggestion_ready", "")])


def _event(
    event_id: int,
    event_type: str,
    payload: dict[str, object],
    kind: str | None = None,
) -> BehaviorEvent:
    return BehaviorEvent(
        id=event_id,
        event_type=event_type,
        kind=kind,
        payload=payload,
        created_at="2026-07-25T12:00:00+00:00",
    )


if __name__ == "__main__":
    unittest.main()
