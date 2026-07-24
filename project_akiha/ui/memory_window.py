"""Memory management window for Phase 3."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from project_akiha.core.memory import MemoryEntry, PendingMemory


class MemoryWindow(QWidget):
    """Small window for reviewing and deleting saved memories."""

    refresh_requested = Signal()
    edit_requested = Signal(int, str, int, object)
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
        self._memory_filter_input = QLineEdit()
        self._memory_filter_input.setPlaceholderText("Search saved memories")
        self._memory_filter_input.textChanged.connect(self._apply_memory_filter)
        self._memory_list = QListWidget()
        self._pending_status_label = QLabel("No pending memories.")
        self._pending_filter_input = QLineEdit()
        self._pending_filter_input.setPlaceholderText("Search pending memories")
        self._pending_filter_input.textChanged.connect(self._apply_pending_filter)
        self._pending_list = QListWidget()
        self._memories: tuple[MemoryEntry, ...] = ()
        self._pending_memories: tuple[PendingMemory, ...] = ()

        tabs = QTabWidget()
        tabs.addTab(_wrap_list(self._memory_filter_input, self._memory_list), "Saved")
        tabs.addTab(
            _wrap_list(self._pending_filter_input, self._pending_list), "Pending"
        )

        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh_requested.emit)

        edit_button = QPushButton("Edit")
        edit_button.clicked.connect(self._request_edit_selected)

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
        button_layout.addWidget(edit_button)
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
        self._memories = memories
        self._memory_list.clear()
        for memory in memories:
            item = QListWidgetItem(_format_memory(memory))
            item.setData(Qt.ItemDataRole.UserRole, memory.id)
            self._memory_list.addItem(item)

        self._apply_memory_filter()

    def update_pending_memories(
        self, pending_memories: tuple[PendingMemory, ...]
    ) -> None:
        """Replace the visible pending memory list."""
        self._pending_memories = pending_memories
        self._pending_list.clear()
        for pending_memory in pending_memories:
            item = QListWidgetItem(_format_pending_memory(pending_memory))
            item.setData(Qt.ItemDataRole.UserRole, pending_memory.id)
            self._pending_list.addItem(item)

        self._apply_pending_filter()

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

    def selected_memory(self) -> MemoryEntry | None:
        """Return the selected memory, if any."""
        memory_id = self.selected_memory_id()
        if memory_id is None:
            return None

        return next(
            (memory for memory in self._memories if memory.id == memory_id),
            None,
        )

    def selected_pending_memory_id(self) -> int | None:
        """Return the selected pending memory id, if any."""
        item = self._pending_list.currentItem()
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        return int(value) if value is not None else None

    def _request_edit_selected(self) -> None:
        memory = self.selected_memory()
        if memory is None:
            self.append_notice("Select a memory first.")
            return

        dialog = MemoryEditDialog(memory, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            content, importance, tags = dialog.values()
            self.edit_requested.emit(memory.id, content, importance, tags)

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

    def _apply_memory_filter(self) -> None:
        query = self._memory_filter_input.text().strip()
        visible_count = _apply_list_filter(self._memory_list, query)
        self._status_label.setText(
            _format_count_status(visible_count, len(self._memories), "memory")
        )

    def _apply_pending_filter(self) -> None:
        query = self._pending_filter_input.text().strip()
        visible_count = _apply_list_filter(self._pending_list, query)
        self._pending_status_label.setText(
            _format_count_status(
                visible_count,
                len(self._pending_memories),
                "pending memory",
            )
        )


class MemoryEditDialog(QDialog):
    """Dialog for correcting a saved memory."""

    def __init__(self, memory: MemoryEntry, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setWindowTitle("Edit Memory")
        self.setMinimumWidth(420)

        self._content_input = QTextEdit()
        self._content_input.setPlainText(memory.content)
        self._content_input.setMinimumHeight(90)

        self._importance_input = QSpinBox()
        self._importance_input.setRange(1, 5)
        self._importance_input.setValue(memory.importance)

        self._tags_input = QLineEdit(", ".join(memory.tags))
        self._tags_input.setPlaceholderText("preference, tool, style")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)

        form_layout = QFormLayout()
        form_layout.addRow("Memory", self._content_input)
        form_layout.addRow("Importance", self._importance_input)
        form_layout.addRow("Tags", self._tags_input)

        layout = QVBoxLayout()
        layout.addLayout(form_layout)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def values(self) -> tuple[str, int, tuple[str, ...]]:
        """Return edited memory values."""
        return (
            self._content_input.toPlainText().strip(),
            self._importance_input.value(),
            _parse_tags(self._tags_input.text()),
        )

    def _accept_if_valid(self) -> None:
        content, _, _ = self.values()
        if not content:
            QMessageBox.warning(self, "Edit memory", "Memory cannot be empty.")
            return

        self.accept()


def _format_memory(memory: MemoryEntry) -> str:
    tags = f" [{', '.join(memory.tags)}]" if memory.tags else ""
    return f"#{memory.id}  Importance {memory.importance}  {memory.content}{tags}"


def _format_pending_memory(pending_memory: PendingMemory) -> str:
    candidate = pending_memory.candidate
    tags = f" [{', '.join(candidate.tags)}]" if candidate.tags else ""
    prefix = f"#{pending_memory.id}  Importance {candidate.importance}"
    return f"{prefix}  {candidate.content}{tags}"


def _apply_list_filter(memory_list: QListWidget, query: str) -> int:
    normalized_query = query.casefold()
    visible_count = 0
    for index in range(memory_list.count()):
        item = memory_list.item(index)
        is_match = not normalized_query or normalized_query in item.text().casefold()
        item.setHidden(not is_match)
        if is_match:
            visible_count += 1

    current_item = memory_list.currentItem()
    if current_item is not None and current_item.isHidden():
        memory_list.setCurrentRow(-1)

    return visible_count


def _format_count_status(visible_count: int, total_count: int, singular: str) -> str:
    plural = _pluralize(singular)
    noun = singular if total_count == 1 else plural
    if visible_count == total_count:
        return f"{total_count} {noun}"

    return f"{visible_count} of {total_count} {noun}"


def _pluralize(singular: str) -> str:
    if singular.endswith("memory"):
        return f"{singular.removesuffix('memory')}memories"
    return f"{singular}s"


def _parse_tags(value: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(tag.strip().lower() for tag in value.split(",") if tag.strip())
    )


def _wrap_list(search_input: QLineEdit, memory_list: QListWidget) -> QWidget:
    widget = QWidget()
    layout = QVBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(search_input)
    layout.addWidget(memory_list)
    widget.setLayout(layout)
    return widget
