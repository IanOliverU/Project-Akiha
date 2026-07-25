"""Behavior history viewer for Phase 5."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from project_akiha.core.behavior import BehaviorEvent


class BehaviorHistoryWindow(QWidget):
    """Window for inspecting recorded companion behavior events."""

    refresh_requested = Signal()
    clear_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setWindowTitle("Akiha Behavior History")
        self.setMinimumSize(620, 420)

        self._events: tuple[BehaviorEvent, ...] = ()
        self._status_label = QLabel("No behavior events loaded.")
        self._filter_input = QLineEdit()
        self._filter_input.setPlaceholderText("Search behavior history")
        self._filter_input.textChanged.connect(self._apply_filter)

        self._event_list = QListWidget()
        self._event_list.currentItemChanged.connect(self._show_selected_details)

        self._details_input = QPlainTextEdit()
        self._details_input.setReadOnly(True)
        self._details_input.setPlaceholderText("Select an event to inspect details.")

        splitter = QSplitter()
        splitter.addWidget(self._event_list)
        splitter.addWidget(self._details_input)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)

        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh_requested.emit)

        clear_button = QPushButton("Clear all")
        clear_button.clicked.connect(self._request_clear_all)

        button_layout = QHBoxLayout()
        button_layout.addWidget(refresh_button)
        button_layout.addWidget(clear_button)
        button_layout.addStretch()

        layout = QVBoxLayout()
        layout.addWidget(self._status_label)
        layout.addWidget(self._filter_input)
        layout.addWidget(splitter)
        layout.addLayout(button_layout)
        self.setLayout(layout)

    def update_events(self, events: tuple[BehaviorEvent, ...]) -> None:
        """Replace the visible behavior history."""
        self._events = events
        self._event_list.clear()

        for event in events:
            item = QListWidgetItem(_format_event_summary(event))
            item.setData(Qt.ItemDataRole.UserRole, event.id)
            item.setData(Qt.ItemDataRole.UserRole + 1, _search_text(event))
            self._event_list.addItem(item)

        self._apply_filter()
        if self._event_list.count() > 0:
            self._event_list.setCurrentRow(0)
        else:
            self._details_input.clear()

    def append_notice(self, message: str) -> None:
        """Show a short status message."""
        self._status_label.setText(message)

    def selected_event_id(self) -> int | None:
        """Return the selected behavior event id, if any."""
        item = self._event_list.currentItem()
        if item is None:
            return None

        value = item.data(Qt.ItemDataRole.UserRole)
        return int(value) if value is not None else None

    def selected_event(self) -> BehaviorEvent | None:
        """Return the selected behavior event, if any."""
        event_id = self.selected_event_id()
        if event_id is None:
            return None

        return next((event for event in self._events if event.id == event_id), None)

    def _request_clear_all(self) -> None:
        answer = QMessageBox.question(
            self,
            "Clear behavior history",
            "Delete all behavior history events?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.clear_requested.emit()

    def _apply_filter(self) -> None:
        query = self._filter_input.text().strip().casefold()
        visible_count = 0
        first_visible_row: int | None = None

        for index in range(self._event_list.count()):
            item = self._event_list.item(index)
            search_text = str(item.data(Qt.ItemDataRole.UserRole + 1)).casefold()
            is_match = not query or query in search_text
            item.setHidden(not is_match)
            if is_match:
                visible_count += 1
                if first_visible_row is None:
                    first_visible_row = index

        current_item = self._event_list.currentItem()
        if current_item is not None and current_item.isHidden():
            row = first_visible_row if first_visible_row is not None else -1
            self._event_list.setCurrentRow(row)

        if visible_count == 0:
            self._details_input.clear()

        self._status_label.setText(
            _format_count_status(visible_count, len(self._events))
        )

    def _show_selected_details(
        self,
        current: QListWidgetItem | None,
        previous: QListWidgetItem | None,
    ) -> None:
        del previous
        if current is None or current.isHidden():
            self._details_input.clear()
            return

        event = self.selected_event()
        if event is None:
            self._details_input.clear()
            return

        self._details_input.setPlainText(_format_event_details(event))


def _format_event_summary(event: BehaviorEvent) -> str:
    kind = f"  {event.kind}" if event.kind else ""
    message = _first_payload_value(
        event.payload,
        ("message", "reason", "channel", "decision_reason"),
    )
    suffix = f"  {message}" if message else ""
    return f"#{event.id}  {event.created_at}  {event.event_type}{kind}{suffix}"


def _format_event_details(event: BehaviorEvent) -> str:
    lines = [
        f"ID: {event.id}",
        f"Created: {event.created_at}",
        f"Event type: {event.event_type}",
        f"Kind: {event.kind or 'None'}",
        "",
        "Payload:",
        _format_payload(event.payload),
    ]
    return "\n".join(lines)


def _format_payload(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, default=str)


def _search_text(event: BehaviorEvent) -> str:
    parts: Iterable[str] = (
        str(event.id),
        event.created_at,
        event.event_type,
        event.kind or "",
        _format_payload(event.payload),
    )
    return " ".join(parts)


def _first_payload_value(payload: Any, keys: tuple[str, ...]) -> str | None:
    if not isinstance(payload, dict):
        return None

    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return None


def _format_count_status(visible_count: int, total_count: int) -> str:
    noun = "event" if total_count == 1 else "events"
    if visible_count == total_count:
        return f"{total_count} behavior {noun}"

    return f"{visible_count} of {total_count} behavior {noun}"
