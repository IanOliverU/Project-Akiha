"""Memory management window for Phase 3."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from project_akiha.core.memory import MemoryEntry, PendingMemory


class MemoryWindow(QWidget):
    """Small window for reviewing and deleting saved memories."""

    refresh_requested = Signal()
    delete_requested = Signal(int)
    clear_requested = Signal()
    approve_requested = Signal(int)
    reject_requested = Signal(int)
    clear_pending_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setWindowTitle("Akiha Memories")
        self.setMinimumSize(520, 420)

        self._status_label = QLabel("No memories loaded.")
        self._memory_list = QListWidget()
        self._pending_status_label = QLabel("No pending memories.")
        self._pending_list = QListWidget()

        tabs = QTabWidget()
        tabs.addTab(_wrap_list(self._memory_list), "Saved")
        tabs.addTab(_wrap_list(self._pending_list), "Pending")

        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh_requested.emit)

        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(self._request_delete_selected)

        clear_button = QPushButton("Clear all")
        clear_button.clicked.connect(self._request_clear_all)

        approve_button = QPushButton("Approve")
        approve_button.clicked.connect(self._request_approve_selected)

        reject_button = QPushButton("Reject")
        reject_button.clicked.connect(self._request_reject_selected)

        clear_pending_button = QPushButton("Clear pending")
        clear_pending_button.clicked.connect(self.clear_pending_requested.emit)

        button_layout = QHBoxLayout()
        button_layout.addWidget(refresh_button)
        button_layout.addWidget(delete_button)
        button_layout.addWidget(clear_button)
        button_layout.addWidget(approve_button)
        button_layout.addWidget(reject_button)
        button_layout.addWidget(clear_pending_button)
        button_layout.addStretch()

        layout = QVBoxLayout()
        layout.addWidget(self._status_label)
        layout.addWidget(self._pending_status_label)
        layout.addWidget(tabs)
        layout.addLayout(button_layout)
        self.setLayout(layout)

    def update_memories(self, memories: tuple[MemoryEntry, ...]) -> None:
        """Replace the visible memory list."""
        self._memory_list.clear()
        for memory in memories:
            item = QListWidgetItem(_format_memory(memory))
            item.setData(Qt.ItemDataRole.UserRole, memory.id)
            self._memory_list.addItem(item)

        count = len(memories)
        noun = "memory" if count == 1 else "memories"
        self._status_label.setText(f"{count} {noun}")

    def update_pending_memories(
        self, pending_memories: tuple[PendingMemory, ...]
    ) -> None:
        """Replace the visible pending memory list."""
        self._pending_list.clear()
        for pending_memory in pending_memories:
            item = QListWidgetItem(_format_pending_memory(pending_memory))
            item.setData(Qt.ItemDataRole.UserRole, pending_memory.id)
            self._pending_list.addItem(item)

        count = len(pending_memories)
        noun = "pending memory" if count == 1 else "pending memories"
        self._pending_status_label.setText(f"{count} {noun}")

    def append_notice(self, message: str) -> None:
        """Show a short status message."""
        self._status_label.setText(message)

    def selected_memory_id(self) -> int | None:
        """Return the selected memory id, if any."""
        item = self._memory_list.currentItem()
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        return int(value) if value is not None else None

    def selected_pending_memory_id(self) -> int | None:
        """Return the selected pending memory id, if any."""
        item = self._pending_list.currentItem()
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        return int(value) if value is not None else None

    def _request_delete_selected(self) -> None:
        memory_id = self.selected_memory_id()
        if memory_id is None:
            self.append_notice("Select a memory first.")
            return

        answer = QMessageBox.question(
            self,
            "Delete memory",
            "Delete the selected memory?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.delete_requested.emit(memory_id)

    def _request_clear_all(self) -> None:
        answer = QMessageBox.question(
            self,
            "Clear memories",
            "Delete all saved memories?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.clear_requested.emit()

    def _request_approve_selected(self) -> None:
        pending_memory_id = self.selected_pending_memory_id()
        if pending_memory_id is None:
            self.append_notice("Select a pending memory first.")
            return

        self.approve_requested.emit(pending_memory_id)

    def _request_reject_selected(self) -> None:
        pending_memory_id = self.selected_pending_memory_id()
        if pending_memory_id is None:
            self.append_notice("Select a pending memory first.")
            return

        self.reject_requested.emit(pending_memory_id)


def _format_memory(memory: MemoryEntry) -> str:
    tags = f" [{', '.join(memory.tags)}]" if memory.tags else ""
    return f"#{memory.id}  Importance {memory.importance}  {memory.content}{tags}"


def _format_pending_memory(pending_memory: PendingMemory) -> str:
    candidate = pending_memory.candidate
    tags = f" [{', '.join(candidate.tags)}]" if candidate.tags else ""
    prefix = f"#{pending_memory.id}  Importance {candidate.importance}"
    return f"{prefix}  {candidate.content}{tags}"


def _wrap_list(memory_list: QListWidget) -> QWidget:
    widget = QWidget()
    layout = QVBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(memory_list)
    widget.setLayout(layout)
    return widget
