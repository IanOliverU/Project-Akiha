"""Memory management window for Phase 3."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
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
from project_akiha.ui.fluent_icons import fluent_icon
from project_akiha.ui.manager_presentation import (
    ITEM_ACCENT_ROLE,
    ITEM_META_ROLE,
    ITEM_TAGS_ROLE,
    ITEM_TITLE_ROLE,
    MemoryItemDelegate,
)
from project_akiha.ui.theme import AKIHA_PALETTE, memory_window_stylesheet


class MemoryWindow(QWidget):
    """Small window for reviewing and deleting saved memories."""

    refresh_requested = Signal()
    edit_requested = Signal(int, str, int, object)
    archive_requested = Signal(int)
    restore_requested = Signal(int)
    delete_requested = Signal(int)
    clear_requested = Signal()
    reflect_requested = Signal()
    approve_requested = Signal(int)
    reject_requested = Signal(int)
    clear_pending_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setWindowTitle("Akiha Memories")
        self.setObjectName("akihaMemoryWindow")
        self.setMinimumSize(760, 500)
        self.resize(920, 640)
        self.setStyleSheet(memory_window_stylesheet())

        self._status_label = QLabel("No memories loaded.")
        self._status_label.setObjectName("managerStatus")
        self._memory_filter_input = QLineEdit()
        self._memory_filter_input.setObjectName("managerSearchInput")
        self._memory_filter_input.setPlaceholderText("Search saved memories")
        self._memory_filter_input.addAction(
            fluent_icon("\ue721"),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self._memory_filter_input.textChanged.connect(self._apply_memory_filter)
        self._memory_list = QListWidget()
        self._memory_list.setObjectName("memoryCardList")
        self._memory_list.setItemDelegate(MemoryItemDelegate(self._memory_list))
        self._archived_status_label = QLabel("No archived memories.")
        self._archived_status_label.setObjectName("managerStatus")
        self._archived_filter_input = QLineEdit()
        self._archived_filter_input.setObjectName("managerSearchInput")
        self._archived_filter_input.setPlaceholderText("Search archived memories")
        self._archived_filter_input.addAction(
            fluent_icon("\ue721"),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self._archived_filter_input.textChanged.connect(self._apply_archived_filter)
        self._archived_list = QListWidget()
        self._archived_list.setObjectName("memoryCardList")
        self._archived_list.setItemDelegate(MemoryItemDelegate(self._archived_list))
        self._pending_status_label = QLabel("No pending memories.")
        self._pending_status_label.setObjectName("managerStatus")
        self._pending_filter_input = QLineEdit()
        self._pending_filter_input.setObjectName("managerSearchInput")
        self._pending_filter_input.setPlaceholderText("Search pending memories")
        self._pending_filter_input.addAction(
            fluent_icon("\ue721"),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self._pending_filter_input.textChanged.connect(self._apply_pending_filter)
        self._pending_list = QListWidget()
        self._pending_list.setObjectName("memoryCardList")
        self._pending_list.setItemDelegate(MemoryItemDelegate(self._pending_list))
        self._memories: tuple[MemoryEntry, ...] = ()
        self._archived_memories: tuple[MemoryEntry, ...] = ()
        self._pending_memories: tuple[PendingMemory, ...] = ()

        tabs = QTabWidget()
        tabs.setObjectName("managerTabContainer")
        tabs.tabBar().setObjectName("managerTabs")
        tabs.setDocumentMode(True)
        tabs.addTab(_wrap_list(self._memory_filter_input, self._memory_list), "Saved")
        tabs.addTab(
            _wrap_list(self._archived_filter_input, self._archived_list), "Archived"
        )
        tabs.addTab(
            _wrap_list(self._pending_filter_input, self._pending_list), "Pending"
        )
        tabs.currentChanged.connect(self._sync_action_buttons)
        self._tabs = tabs

        refresh_button = QPushButton("Refresh")
        refresh_button.setIcon(fluent_icon("\ue72c"))
        refresh_button.clicked.connect(self.refresh_requested.emit)

        edit_button = QPushButton("Edit")
        edit_button.setIcon(fluent_icon("\ue70f"))
        edit_button.clicked.connect(self._request_edit_selected)

        archive_button = QPushButton("Archive")
        archive_button.setIcon(fluent_icon("\ue7b8"))
        archive_button.clicked.connect(self._request_archive_selected)

        restore_button = QPushButton("Restore")
        restore_button.setIcon(fluent_icon("\ue777"))
        restore_button.clicked.connect(self._request_restore_selected)

        delete_button = QPushButton("Delete")
        delete_button.setObjectName("dangerButton")
        delete_button.setIcon(fluent_icon("\ue74d"))
        delete_button.clicked.connect(self._request_delete_selected)

        clear_button = QPushButton("Clear all")
        clear_button.setObjectName("dangerButton")
        clear_button.setIcon(fluent_icon("\ue74d"))
        clear_button.clicked.connect(self._request_clear_all)

        reflect_button = QPushButton("Reflect")
        reflect_button.setObjectName("primaryButton")
        reflect_button.setIcon(fluent_icon("\ue895"))
        reflect_button.clicked.connect(self.reflect_requested.emit)

        approve_button = QPushButton("Approve")
        approve_button.setObjectName("primaryButton")
        approve_button.setIcon(fluent_icon("\ue73e"))
        approve_button.clicked.connect(self._request_approve_selected)

        reject_button = QPushButton("Reject")
        reject_button.setObjectName("dangerButton")
        reject_button.setIcon(fluent_icon("\ue711"))
        reject_button.clicked.connect(self._request_reject_selected)

        clear_pending_button = QPushButton("Clear pending")
        clear_pending_button.setObjectName("dangerButton")
        clear_pending_button.setIcon(fluent_icon("\ue74d"))
        clear_pending_button.clicked.connect(self.clear_pending_requested.emit)

        self._memory_action_buttons = {
            "refresh": refresh_button,
            "edit": edit_button,
            "archive": archive_button,
            "restore": restore_button,
            "delete": delete_button,
            "clear": clear_button,
            "reflect": reflect_button,
            "approve": approve_button,
            "reject": reject_button,
            "clear_pending": clear_pending_button,
        }

        button_layout = QHBoxLayout()
        button_layout.addWidget(refresh_button)
        button_layout.addWidget(edit_button)
        button_layout.addWidget(archive_button)
        button_layout.addWidget(restore_button)
        button_layout.addWidget(approve_button)
        button_layout.addWidget(reject_button)
        button_layout.addWidget(clear_pending_button)
        button_layout.addStretch(1)
        button_layout.addWidget(delete_button)
        button_layout.addWidget(clear_button)
        button_layout.addWidget(reflect_button)

        title_label = QLabel()
        title_label.setPixmap(fluent_icon("\ue70c", 20).pixmap(22, 22))
        title_text = QLabel("Akiha Memories")
        title_text.setObjectName("managerTitle")
        close_button = QPushButton()
        close_button.setObjectName("closeButton")
        close_button.setIcon(fluent_icon("\ue8bb"))
        close_button.setToolTip("Close")
        close_button.clicked.connect(self.close)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(9)
        title_row.addWidget(title_label)
        title_row.addWidget(title_text)
        title_row.addStretch(1)

        stats_row = QHBoxLayout()
        stats_row.setContentsMargins(0, 0, 0, 0)
        stats_row.setSpacing(6)
        memory_dot = QLabel("●")
        memory_dot.setObjectName("managerStatusDot")
        archived_dot = QLabel("○")
        archived_dot.setObjectName("managerStatusDotMuted")
        stats_row.addWidget(memory_dot)
        stats_row.addWidget(self._status_label)
        stats_row.addSpacing(12)
        stats_row.addWidget(archived_dot)
        stats_row.addWidget(self._archived_status_label)
        stats_row.addStretch(1)

        heading_layout = QVBoxLayout()
        heading_layout.setContentsMargins(0, 0, 0, 0)
        heading_layout.setSpacing(7)
        heading_layout.addLayout(title_row)
        heading_layout.addLayout(stats_row)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(22, 16, 16, 16)
        header_layout.addLayout(heading_layout)
        header_layout.addStretch(1)
        header_layout.addWidget(close_button, 0, Qt.AlignmentFlag.AlignTop)
        header = QFrame()
        header.setObjectName("managerHeader")
        header.setLayout(header_layout)

        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(16, 10, 16, 10)
        footer_layout.addLayout(button_layout)
        footer = QFrame()
        footer.setObjectName("managerFooter")
        footer.setLayout(footer_layout)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header)
        layout.addWidget(tabs)
        layout.addWidget(footer)
        self.setLayout(layout)
        self._sync_action_buttons(0)

    def _sync_action_buttons(self, tab_index: int) -> None:
        visible_actions = {
            0: {"refresh", "edit", "archive", "delete", "reflect"},
            1: {"refresh", "restore"},
            2: {"refresh", "approve", "reject", "clear_pending"},
        }.get(tab_index, {"refresh"})
        for name, button in self._memory_action_buttons.items():
            button.setVisible(name in visible_actions)

    def update_memories(self, memories: tuple[MemoryEntry, ...]) -> None:
        """Replace the visible memory list."""
        self._memories = memories
        self._memory_list.clear()
        for memory in memories:
            item = QListWidgetItem(_format_memory(memory))
            item.setData(Qt.ItemDataRole.UserRole, memory.id)
            _present_memory_item(item, memory)
            self._memory_list.addItem(item)

        self._apply_memory_filter()

    def update_archived_memories(self, memories: tuple[MemoryEntry, ...]) -> None:
        """Replace the visible archived memory list."""
        self._archived_memories = memories
        self._archived_list.clear()
        for memory in memories:
            item = QListWidgetItem(_format_memory(memory))
            item.setData(Qt.ItemDataRole.UserRole, memory.id)
            _present_memory_item(item, memory, state="archived")
            self._archived_list.addItem(item)

        self._apply_archived_filter()

    def update_pending_memories(
        self, pending_memories: tuple[PendingMemory, ...]
    ) -> None:
        """Replace the visible pending memory list."""
        self._pending_memories = pending_memories
        self._pending_list.clear()
        for pending_memory in pending_memories:
            item = QListWidgetItem(_format_pending_memory(pending_memory))
            item.setData(Qt.ItemDataRole.UserRole, pending_memory.id)
            _present_pending_memory_item(item, pending_memory)
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

    def selected_archived_memory_id(self) -> int | None:
        """Return the selected archived memory id, if any."""
        item = self._archived_list.currentItem()
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

    def _request_edit_selected(self) -> None:
        memory = self.selected_memory()
        if memory is None:
            self.append_notice("Select a memory first.")
            return

        dialog = MemoryEditDialog(memory, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            content, importance, tags = dialog.values()
            self.edit_requested.emit(memory.id, content, importance, tags)

    def _request_archive_selected(self) -> None:
        memory_id = self.selected_memory_id()
        if memory_id is None:
            self.append_notice("Select a memory first.")
            return

        self.archive_requested.emit(memory_id)

    def _request_restore_selected(self) -> None:
        memory_id = self.selected_archived_memory_id()
        if memory_id is None:
            self.append_notice("Select an archived memory first.")
            return

        self.restore_requested.emit(memory_id)

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
        self._tabs.setTabText(0, "Saved")

    def _apply_archived_filter(self) -> None:
        query = self._archived_filter_input.text().strip()
        visible_count = _apply_list_filter(self._archived_list, query)
        self._archived_status_label.setText(
            _format_count_status(
                visible_count,
                len(self._archived_memories),
                "archived memory",
            )
        )
        self._tabs.setTabText(1, "Archived")

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
        pending_count = len(self._pending_memories)
        pending_label = f"Pending {pending_count}" if pending_count else "Pending"
        self._tabs.setTabText(2, pending_label)


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


def _present_memory_item(
    item: QListWidgetItem,
    memory: MemoryEntry,
    *,
    state: str = "saved",
) -> None:
    state_label = "ARCHIVED  ·  " if state == "archived" else ""
    item.setData(ITEM_TITLE_ROLE, memory.content)
    item.setData(
        ITEM_META_ROLE,
        f"{state_label}Imp {memory.importance}",
    )
    item.setData(ITEM_TAGS_ROLE, memory.tags or ("untagged",))
    item.setData(
        ITEM_ACCENT_ROLE,
        "#E0C561" if memory.importance >= 4 else AKIHA_PALETTE.highlight,
    )


def _present_pending_memory_item(
    item: QListWidgetItem,
    pending_memory: PendingMemory,
) -> None:
    candidate = pending_memory.candidate
    item.setData(ITEM_TITLE_ROLE, candidate.content)
    item.setData(
        ITEM_META_ROLE,
        f"Pending  ·  Imp {candidate.importance}",
    )
    item.setData(ITEM_TAGS_ROLE, candidate.tags or ("untagged",))
    item.setData(ITEM_ACCENT_ROLE, "#E0C561")


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
    layout.setContentsMargins(16, 12, 16, 12)
    layout.setSpacing(10)
    layout.addWidget(search_input)
    layout.addWidget(memory_list)
    widget.setLayout(layout)
    return widget
