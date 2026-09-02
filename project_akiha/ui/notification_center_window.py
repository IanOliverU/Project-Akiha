"""Privacy-safe Notification Center for external awareness events."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from project_akiha.core.notifications import NotificationInboxRecord
from project_akiha.ui.fluent_icons import fluent_icon
from project_akiha.ui.theme import AKIHA_PALETTE, manager_window_stylesheet


class NotificationCenterWindow(QWidget):
    """Inspect and manage bounded sanitized notification records."""

    refresh_requested = Signal()
    mark_read_requested = Signal(tuple)
    mark_all_read_requested = Signal()
    clear_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Akiha Notifications")
        self.setObjectName("akihaNotificationCenterWindow")
        self.setMinimumSize(620, 440)
        self.resize(760, 560)
        self.setStyleSheet(manager_window_stylesheet(self.objectName()))
        self._records: tuple[NotificationInboxRecord, ...] = ()

        self._status_label = QLabel("No notifications loaded.")
        self._status_label.setObjectName("managerStatus")
        self._list = QListWidget()
        self._list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._list.itemDoubleClicked.connect(lambda _item: self._mark_selected_read())

        title = QLabel("Akiha Notifications")
        title.setObjectName("managerTitle")
        icon = QLabel()
        icon.setPixmap(fluent_icon("\ue7f4", 20).pixmap(22, 22))
        close_button = QPushButton()
        close_button.setObjectName("closeButton")
        close_button.setIcon(fluent_icon("\ue8bb"))
        close_button.setToolTip("Close")
        close_button.clicked.connect(self.close)

        title_row = QHBoxLayout()
        title_row.setSpacing(9)
        title_row.addWidget(icon)
        title_row.addWidget(title)
        title_row.addStretch(1)
        title_row.addWidget(close_button)

        heading = QVBoxLayout()
        heading.setSpacing(6)
        heading.addLayout(title_row)
        heading.addWidget(self._status_label)
        header = QFrame()
        header.setObjectName("managerHeader")
        header.setLayout(heading)
        heading.setContentsMargins(22, 14, 16, 14)

        refresh = QPushButton("Refresh")
        refresh.setIcon(fluent_icon("\ue72c"))
        refresh.clicked.connect(self.refresh_requested.emit)
        mark_read = QPushButton("Mark read")
        mark_read.clicked.connect(self._mark_selected_read)
        mark_all = QPushButton("Mark all read")
        mark_all.clicked.connect(self.mark_all_read_requested.emit)
        clear = QPushButton("Clear all")
        clear.setObjectName("dangerButton")
        clear.setIcon(fluent_icon("\ue74d"))
        clear.clicked.connect(self._request_clear)
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(16, 10, 16, 10)
        footer_layout.addWidget(refresh)
        footer_layout.addWidget(mark_read)
        footer_layout.addWidget(mark_all)
        footer_layout.addStretch(1)
        footer_layout.addWidget(clear)
        footer = QFrame()
        footer.setObjectName("managerFooter")
        footer.setLayout(footer_layout)

        body = QFrame()
        body.setObjectName("managerBody")
        body_layout = QVBoxLayout()
        body_layout.setContentsMargins(16, 14, 16, 14)
        body_layout.addWidget(self._list)
        body.setLayout(body_layout)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header)
        layout.addWidget(body, 1)
        layout.addWidget(footer)
        self.setLayout(layout)

    def update_records(self, records: tuple[NotificationInboxRecord, ...]) -> None:
        """Replace the visible sanitized records."""
        self._records = records
        self._list.clear()
        unread = 0
        for record in records:
            if record.read_at is None:
                unread += 1
            count = f" ({record.aggregate_count})" if record.aggregate_count > 1 else ""
            state = "Unread" if record.read_at is None else "Read"
            item = QListWidgetItem(
                f"{record.service.value.upper()}  {record.display_text}{count}\n"
                f"{record.occurred_at.astimezone().strftime('%Y-%m-%d %H:%M')}  "
                f"{record.priority.value.title()}  {state}"
            )
            item.setData(Qt.ItemDataRole.UserRole, record.id)
            item.setForeground(QBrush(QColor(_priority_color(record.priority.value))))
            if record.read_at is None:
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            item.setToolTip(record.event_kind.value)
            self._list.addItem(item)
        noun = "notification" if len(records) == 1 else "notifications"
        self._status_label.setText(f"{len(records)} {noun}, {unread} unread")

    def append_notice(self, message: str) -> None:
        self._status_label.setText(message)

    def _mark_selected_read(self) -> None:
        ids = tuple(
            int(item.data(Qt.ItemDataRole.UserRole))
            for item in self._list.selectedItems()
        )
        if ids:
            self.mark_read_requested.emit(ids)

    def _request_clear(self) -> None:
        answer = QMessageBox.question(
            self,
            "Clear notifications",
            "Delete all sanitized notification history? Integration credentials "
            "and deduplication receipts will remain.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.clear_requested.emit()


def _priority_color(priority: str) -> str:
    if priority == "critical":
        return AKIHA_PALETTE.error
    if priority == "important":
        return "#E0C561"
    if priority == "low":
        return AKIHA_PALETTE.muted_text
    return AKIHA_PALETTE.text
