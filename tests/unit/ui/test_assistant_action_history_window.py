"""Tests for assistant-action search-result and audit presentation."""

from __future__ import annotations

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from project_akiha.core.actions import (
    ActionAuditEntry,
    ActionFailureCategory,
    ActionStatus,
    FileSearchMatch,
    PermissionDecision,
)
from project_akiha.ui.assistant_action_history_window import (
    AssistantActionHistoryWindow,
)


class AssistantActionHistoryWindowTest(unittest.TestCase):
    """Verify action results and audit entries remain bounded and inspectable."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication(sys.argv)

    def test_presents_search_metadata_without_file_contents(self) -> None:
        window = AssistantActionHistoryWindow()
        match = FileSearchMatch(
            name="notes.txt",
            path=r"C:\Users\Akiha\Documents\notes.txt",
            size_bytes=42,
            modified_at="2026-07-30T12:00:00+00:00",
        )

        window.update_search_results((match,), summary="1 matching file")

        self.assertEqual(window._search_list.count(), 1)
        self.assertEqual(window._search_list.currentRow(), 0)
        details = window._search_details.toPlainText()
        self.assertIn("notes.txt", details)
        self.assertIn("42 bytes", details)
        self.assertNotIn("file contents", details)

    def test_filters_audits_by_status_and_action_text(self) -> None:
        window = AssistantActionHistoryWindow()
        window.update_audits(
            (
                _audit(2, "files.search", ActionStatus.SUCCESS),
                _audit(1, "files.open", ActionStatus.DENIED),
            )
        )

        window._audit_status_filter.setCurrentText("denied")

        self.assertTrue(window._audit_list.item(0).isHidden())
        self.assertFalse(window._audit_list.item(1).isHidden())
        self.assertEqual(window._status_label.text(), "1 of 2 audit entries")

        window._audit_status_filter.setCurrentText("All statuses")
        window._audit_filter.setText("search")

        self.assertFalse(window._audit_list.item(0).isHidden())
        self.assertTrue(window._audit_list.item(1).isHidden())

    def test_audit_details_exclude_untrusted_payloads(self) -> None:
        window = AssistantActionHistoryWindow()
        window.update_audits((_audit(1, "files.search", ActionStatus.SUCCESS),))

        details = window._audit_details.toPlainText()

        self.assertIn("Action: files.search", details)
        self.assertIn("Result: success", details)
        self.assertNotIn("secret provider content", details)


def _audit(audit_id: int, action_id: str, status: ActionStatus) -> ActionAuditEntry:
    return ActionAuditEntry(
        id=audit_id,
        correlation_id=f"request-{audit_id}",
        action_id=action_id,
        source="chat",
        normalized_target=r"C:\Users\Akiha\Documents",
        permission_decision=(
            PermissionDecision.GRANTED
            if status is ActionStatus.SUCCESS
            else PermissionDecision.MISSING
        ),
        result_status=status,
        duration_ms=12,
        failure_category=(
            None
            if status is ActionStatus.SUCCESS
            else ActionFailureCategory.PERMISSION_REQUIRED
        ),
        created_at="2026-07-30T12:00:00+00:00",
    )


if __name__ == "__main__":
    unittest.main()
