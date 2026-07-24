"""Tests for the memory manager window."""

from __future__ import annotations

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from project_akiha.core.memory import MemoryCandidate, MemoryEntry, PendingMemory
from project_akiha.ui.memory_window import MemoryEditDialog, MemoryWindow, _parse_tags


class MemoryWindowTest(unittest.TestCase):
    """Verify memory manager filtering behavior."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication(sys.argv)

    def test_filters_saved_memories_by_content_or_tag(self) -> None:
        window = MemoryWindow()
        window.update_memories(
            (
                _memory(1, "User prefers concise replies.", tags=("preference",)),
                _memory(2, "User uses Krita.", tags=("tool",)),
            )
        )

        window._memory_filter_input.setText("krita")

        self.assertTrue(window._memory_list.item(0).isHidden())
        self.assertFalse(window._memory_list.item(1).isHidden())
        self.assertEqual(window._status_label.text(), "1 of 2 memories")

        window._memory_filter_input.setText("preference")

        self.assertFalse(window._memory_list.item(0).isHidden())
        self.assertTrue(window._memory_list.item(1).isHidden())

    def test_filters_pending_memories(self) -> None:
        window = MemoryWindow()
        window.update_pending_memories(
            (
                _pending_memory(1, "User likes dark mode."),
                _pending_memory(2, "User uses Blender."),
            )
        )

        window._pending_filter_input.setText("blender")

        self.assertTrue(window._pending_list.item(0).isHidden())
        self.assertFalse(window._pending_list.item(1).isHidden())
        self.assertEqual(
            window._pending_status_label.text(),
            "1 of 2 pending memories",
        )

    def test_filters_archived_memories(self) -> None:
        window = MemoryWindow()
        window.update_archived_memories(
            (
                _memory(1, "User prefers concise replies."),
                _memory(2, "User uses Krita."),
            )
        )

        window._archived_filter_input.setText("krita")

        self.assertTrue(window._archived_list.item(0).isHidden())
        self.assertFalse(window._archived_list.item(1).isHidden())
        self.assertEqual(
            window._archived_status_label.text(),
            "1 of 2 archived memories",
        )

    def test_filter_clears_hidden_saved_selection(self) -> None:
        window = MemoryWindow()
        window.update_memories(
            (
                _memory(1, "User prefers concise replies."),
                _memory(2, "User uses Krita."),
            )
        )
        window._memory_list.setCurrentRow(0)

        window._memory_filter_input.setText("krita")

        self.assertIsNone(window.selected_memory_id())

    def test_filter_clears_hidden_archived_selection(self) -> None:
        window = MemoryWindow()
        window.update_archived_memories(
            (
                _memory(1, "User prefers concise replies."),
                _memory(2, "User uses Krita."),
            )
        )
        window._archived_list.setCurrentRow(0)

        window._archived_filter_input.setText("krita")

        self.assertIsNone(window.selected_archived_memory_id())

    def test_selected_memory_returns_full_memory_entry(self) -> None:
        window = MemoryWindow()
        window.update_memories(
            (
                _memory(1, "User prefers concise replies."),
                _memory(2, "User uses Krita."),
            )
        )

        window._memory_list.setCurrentRow(1)

        selected = window.selected_memory()
        self.assertIsNotNone(selected)
        self.assertEqual(selected.id, 2)
        self.assertEqual(selected.content, "User uses Krita.")

    def test_selected_archived_memory_id_returns_current_archived_item(self) -> None:
        window = MemoryWindow()
        window.update_archived_memories((_memory(3, "Archived memory."),))

        window._archived_list.setCurrentRow(0)

        self.assertEqual(window.selected_archived_memory_id(), 3)

    def test_edit_dialog_returns_normalized_values(self) -> None:
        dialog = MemoryEditDialog(
            _memory(1, "User prefers concise replies.", tags=("preference",))
        )

        dialog._content_input.setPlainText(" Updated memory. ")
        dialog._importance_input.setValue(5)
        dialog._tags_input.setText("Preference, tool, tool")

        self.assertEqual(
            dialog.values(),
            ("Updated memory.", 5, ("preference", "tool")),
        )

    def test_parse_tags_ignores_empty_and_duplicate_values(self) -> None:
        self.assertEqual(
            _parse_tags(" Preference, , Tool, preference "),
            ("preference", "tool"),
        )


def _memory(
    memory_id: int,
    content: str,
    tags: tuple[str, ...] = (),
) -> MemoryEntry:
    return MemoryEntry(
        id=memory_id,
        content=content,
        source_conversation_id=None,
        importance=3,
        tags=tags,
        created_at="now",
        updated_at="now",
        last_accessed_at=None,
    )


def _pending_memory(pending_memory_id: int, content: str) -> PendingMemory:
    return PendingMemory(
        id=pending_memory_id,
        candidate=MemoryCandidate(content=content, source_role="user"),
        source_conversation_id=None,
    )


if __name__ == "__main__":
    unittest.main()
