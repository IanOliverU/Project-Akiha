"""Behavior history viewer for Phase 5."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
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
from project_akiha.ui.fluent_icons import FluentComboBox, fluent_icon
from project_akiha.ui.manager_presentation import (
    ITEM_ACCENT_ROLE,
    ITEM_TAGS_ROLE,
    ITEM_TIMESTAMP_ROLE,
    ITEM_TITLE_ROLE,
    BehaviorEventDelegate,
    TechnicalDetailsHighlighter,
)
from project_akiha.ui.theme import AKIHA_PALETTE, behavior_history_stylesheet


class BehaviorHistoryWindow(QWidget):
    """Window for inspecting recorded companion behavior events."""

    refresh_requested = Signal()
    clear_requested = Signal()
    clear_matching_requested = Signal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setWindowTitle("Akiha Behavior History")
        self.setObjectName("akihaBehaviorHistoryWindow")
        self.setMinimumSize(760, 500)
        self.resize(1000, 650)
        self.setStyleSheet(behavior_history_stylesheet())

        self._events: tuple[BehaviorEvent, ...] = ()
        self._status_label = QLabel("No behavior events loaded.")
        self._status_label.setObjectName("managerStatus")
        self._filter_input = QLineEdit()
        self._filter_input.setObjectName("managerSearchInput")
        self._filter_input.setPlaceholderText("Search behavior history")
        self._filter_input.addAction(
            fluent_icon("\ue721"),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self._filter_input.textChanged.connect(self._apply_filter)
        self._event_type_filter_input = FluentComboBox()
        self._event_type_filter_input.currentTextChanged.connect(self._apply_filter)
        self._kind_filter_input = FluentComboBox()
        self._kind_filter_input.currentTextChanged.connect(self._apply_filter)
        self._reset_filter_controls()

        self._event_list = QListWidget()
        self._event_list.setObjectName("behaviorEventList")
        self._event_list.setMinimumWidth(330)
        self._event_list.setMaximumWidth(360)
        self._event_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._event_list.setItemDelegate(BehaviorEventDelegate(self._event_list))
        self._event_list.currentItemChanged.connect(self._show_selected_details)

        self._details_title = QLabel("Select an event")
        self._details_title.setObjectName("managerDetailTitle")
        self._details_meta = QLabel("Event metadata will appear here.")
        self._details_meta.setObjectName("managerDetailMeta")
        self._details_badges = QLabel()
        self._details_badges.setObjectName("managerBadge")

        details_heading = QVBoxLayout()
        details_heading.setContentsMargins(0, 0, 0, 0)
        details_heading.setSpacing(3)
        details_heading.addWidget(self._details_title)
        details_heading.addWidget(self._details_meta)

        details_header_layout = QHBoxLayout()
        details_header_layout.setContentsMargins(20, 16, 20, 16)
        details_header_layout.addLayout(details_heading)
        details_header_layout.addStretch(1)
        details_header_layout.addWidget(
            self._details_badges,
            0,
            Qt.AlignmentFlag.AlignTop,
        )
        details_header = QFrame()
        details_header.setObjectName("managerDetailHeader")
        details_header.setLayout(details_header_layout)

        payload_label = QLabel("PAYLOAD")
        payload_label.setObjectName("managerSectionLabel")
        copy_button = QPushButton("Copy")
        copy_button.setObjectName("copyButton")
        copy_button.setIcon(fluent_icon("\ue8c8"))
        copy_button.clicked.connect(self._copy_payload)
        payload_header = QHBoxLayout()
        payload_header.setContentsMargins(20, 14, 20, 8)
        payload_header.addWidget(payload_label)
        payload_header.addStretch(1)
        payload_header.addWidget(copy_button)

        self._details_input = QPlainTextEdit()
        self._details_input.setObjectName("managerCodeBlock")
        self._details_input.setReadOnly(True)
        self._details_input.setPlaceholderText("Select an event to inspect details.")
        self._details_highlighter = TechnicalDetailsHighlighter(
            self._details_input.document()
        )

        details_layout = QVBoxLayout()
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(0)
        details_layout.addWidget(details_header)
        details_layout.addLayout(payload_header)
        details_layout.addWidget(self._details_input, 1)
        details_pane = QFrame()
        details_pane.setObjectName("managerDetailPane")
        details_pane.setLayout(details_layout)

        splitter = QSplitter()
        splitter.addWidget(self._event_list)
        splitter.addWidget(details_pane)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([320, 680])
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        self._splitter = splitter

        refresh_button = QPushButton("Refresh")
        refresh_button.setIcon(fluent_icon("\ue72c"))
        refresh_button.clicked.connect(self.refresh_requested.emit)

        clear_button = QPushButton("Clear all")
        clear_button.setObjectName("dangerButton")
        clear_button.setIcon(fluent_icon("\ue74d"))
        clear_button.clicked.connect(self._request_clear_all)

        clear_matching_button = QPushButton("Clear matching")
        clear_matching_button.clicked.connect(self._request_clear_matching)

        filter_layout = QHBoxLayout()
        filter_layout.setContentsMargins(14, 8, 14, 8)
        filter_layout.setSpacing(10)
        self._event_type_filter_input.setFixedWidth(180)
        self._kind_filter_input.setFixedWidth(140)
        filter_layout.addWidget(self._filter_input, 1)
        filter_layout.addWidget(self._event_type_filter_input)
        filter_layout.addWidget(self._kind_filter_input)

        button_layout = QHBoxLayout()
        button_layout.addWidget(refresh_button)
        button_layout.addStretch(1)
        button_layout.addWidget(clear_matching_button)
        button_layout.addWidget(clear_button)

        icon_label = QLabel()
        icon_label.setPixmap(fluent_icon("\ue81c", 20).pixmap(22, 22))
        title_label = QLabel("Akiha Behavior History")
        title_label.setObjectName("managerTitle")
        close_button = QPushButton()
        close_button.setObjectName("closeButton")
        close_button.setIcon(fluent_icon("\ue8bb"))
        close_button.setToolTip("Close")
        close_button.clicked.connect(self.close)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(9)
        title_row.addWidget(icon_label)
        title_row.addWidget(title_label)
        title_row.addStretch(1)

        heading_layout = QVBoxLayout()
        heading_layout.setContentsMargins(0, 0, 0, 0)
        heading_layout.setSpacing(7)
        heading_layout.addLayout(title_row)
        stats_row = QHBoxLayout()
        stats_row.setContentsMargins(0, 0, 0, 0)
        stats_row.setSpacing(6)
        status_dot = QLabel("●")
        status_dot.setObjectName("managerStatusDot")
        stats_row.addWidget(status_dot)
        stats_row.addWidget(self._status_label)
        stats_row.addStretch(1)
        heading_layout.addLayout(stats_row)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(22, 16, 16, 16)
        header_layout.addLayout(heading_layout)
        header_layout.addStretch(1)
        header_layout.addWidget(close_button, 0, Qt.AlignmentFlag.AlignTop)
        header = QFrame()
        header.setObjectName("managerHeader")
        header.setLayout(header_layout)

        filter_frame = QFrame()
        filter_frame.setObjectName("managerFilters")
        filter_frame.setFixedHeight(56)
        filter_frame.setLayout(filter_layout)

        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(16, 10, 16, 10)
        footer_layout.addLayout(button_layout)
        footer = QFrame()
        footer.setObjectName("managerFooter")
        footer.setFixedHeight(60)
        footer.setLayout(footer_layout)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header)
        layout.addWidget(filter_frame)
        layout.addWidget(splitter, 1)
        layout.addWidget(footer)
        self.setLayout(layout)

    def update_events(self, events: tuple[BehaviorEvent, ...]) -> None:
        """Replace the visible behavior history."""
        selected_event_type = self.selected_event_type_filter()
        selected_kind = self.selected_kind_filter()
        self._events = events
        self._event_list.clear()
        self._populate_filter_options(
            selected_event_type=selected_event_type,
            selected_kind=selected_kind,
        )

        for event in events:
            item = QListWidgetItem(_format_event_summary(event))
            item.setData(Qt.ItemDataRole.UserRole, event.id)
            item.setData(Qt.ItemDataRole.UserRole + 1, _search_text(event))
            item.setData(ITEM_TITLE_ROLE, _friendly_identifier(event.event_type))
            item.setData(ITEM_TIMESTAMP_ROLE, _compact_timestamp(event.created_at))
            item.setData(ITEM_TAGS_ROLE, _behavior_tags(event))
            item.setData(ITEM_ACCENT_ROLE, _event_accent(event))
            self._event_list.addItem(item)

        self._apply_filter()
        first_visible_row = self._first_visible_row()
        if first_visible_row is not None:
            self._event_list.setCurrentRow(first_visible_row)
        else:
            self._event_list.setCurrentRow(-1)
            self._clear_details()

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

    def selected_event_type_filter(self) -> str:
        """Return the selected event-type filter, or an empty all-events filter."""
        return self._selected_filter_value(self._event_type_filter_input)

    def selected_kind_filter(self) -> str:
        """Return the selected kind filter, or an empty all-kinds filter."""
        return self._selected_filter_value(self._kind_filter_input)

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

    def _request_clear_matching(self) -> None:
        event_type = self.selected_event_type_filter()
        kind = self.selected_kind_filter()
        if not event_type and not kind:
            self.append_notice("Choose an event type or kind filter first.")
            return

        label = _format_filter_label(event_type=event_type, kind=kind)
        answer = QMessageBox.question(
            self,
            "Clear matching behavior history",
            f"Delete behavior history matching {label}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.clear_matching_requested.emit(event_type, kind)

    def _apply_filter(self) -> None:
        query = self._filter_input.text().strip().casefold()
        event_type_filter = self.selected_event_type_filter()
        kind_filter = self.selected_kind_filter()
        visible_count = 0
        first_visible_row: int | None = None

        for index in range(self._event_list.count()):
            item = self._event_list.item(index)
            search_text = str(item.data(Qt.ItemDataRole.UserRole + 1)).casefold()
            event = self._event_for_item(item)
            matches_query = not query or query in search_text
            matches_event_type = (
                not event_type_filter
                or event is not None
                and event.event_type == event_type_filter
            )
            matches_kind = (
                not kind_filter or event is not None and event.kind == kind_filter
            )
            is_match = matches_query and matches_event_type and matches_kind
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
            self._clear_details()

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
            self._clear_details()
            return

        event = self.selected_event()
        if event is None:
            self._clear_details()
            return

        self._details_title.setText(_friendly_identifier(event.event_type))
        self._details_meta.setText(f"ID: #{event.id}    Created: {event.created_at}")
        self._details_badges.setText(
            "   ".join(tag.upper() for tag in _behavior_tags(event))
        )
        self._details_input.setPlainText(_format_payload(event.payload))

    def _clear_details(self) -> None:
        self._details_title.setText("Select an event")
        self._details_meta.setText("Event metadata will appear here.")
        self._details_badges.clear()
        self._details_input.clear()

    def _copy_payload(self) -> None:
        payload = self._details_input.toPlainText()
        if payload:
            QGuiApplication.clipboard().setText(payload)
            self.append_notice("Payload copied.")

    def _populate_filter_options(
        self,
        *,
        selected_event_type: str,
        selected_kind: str,
    ) -> None:
        event_types = sorted({event.event_type for event in self._events})
        kinds = sorted({event.kind for event in self._events if event.kind})

        self._replace_combo_values(
            self._event_type_filter_input,
            all_label="All event types",
            values=event_types,
            selected_value=selected_event_type,
        )
        self._replace_combo_values(
            self._kind_filter_input,
            all_label="All kinds",
            values=kinds,
            selected_value=selected_kind,
        )

    def _reset_filter_controls(self) -> None:
        self._replace_combo_values(
            self._event_type_filter_input,
            all_label="All event types",
            values=(),
            selected_value="",
        )
        self._replace_combo_values(
            self._kind_filter_input,
            all_label="All kinds",
            values=(),
            selected_value="",
        )

    def _replace_combo_values(
        self,
        combo: QComboBox,
        *,
        all_label: str,
        values: Iterable[str],
        selected_value: str,
    ) -> None:
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(all_label, "")
        for value in values:
            combo.addItem(value, value)

        if selected_value:
            selected_index = combo.findData(selected_value)
            if selected_index >= 0:
                combo.setCurrentIndex(selected_index)
        combo.blockSignals(False)

    def _selected_filter_value(self, combo: QComboBox) -> str:
        value = combo.currentData()
        return str(value) if value is not None else ""

    def _event_for_item(self, item: QListWidgetItem) -> BehaviorEvent | None:
        value = item.data(Qt.ItemDataRole.UserRole)
        if value is None:
            return None

        event_id = int(value)
        return next((event for event in self._events if event.id == event_id), None)

    def _first_visible_row(self) -> int | None:
        for index in range(self._event_list.count()):
            if not self._event_list.item(index).isHidden():
                return index
        return None


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
        _friendly_identifier(event.event_type),
        "",
        f"ID: #{event.id}",
        f"Created: {event.created_at}",
        f"Event type: {event.event_type}",
        f"Kind: {event.kind or 'None'}",
        "",
        "PAYLOAD:",
        _format_payload(event.payload),
    ]
    return "\n".join(lines)


def _event_accent(event: BehaviorEvent) -> str:
    value = f"{event.event_type} {event.kind or ''}".casefold()
    if any(token in value for token in ("fail", "error", "denied", "blocked")):
        return AKIHA_PALETTE.error
    if any(token in value for token in ("success", "delivered", "completed")):
        return AKIHA_PALETTE.success
    if any(token in value for token in ("proactive", "check_in", "warning")):
        return "#E0C561"
    return AKIHA_PALETTE.highlight


def _friendly_identifier(value: str | None) -> str:
    if not value:
        return "None"
    return value.replace(".", " ").replace("_", " ").title()


def _behavior_tags(event: BehaviorEvent) -> tuple[str, ...]:
    event_family = event.event_type.split(".", maxsplit=1)[0]
    values = [event_family]
    if event.kind:
        values.append(event.kind)
    elif "." in event.event_type:
        event_name = event.event_type.rsplit(".", maxsplit=1)[-1]
        values.append(event_name.rsplit("_", maxsplit=1)[-1])
    return tuple(dict.fromkeys(values))


def _compact_timestamp(value: str) -> str:
    return value.replace("T", " ").removesuffix("+00:00").removesuffix("Z")


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


def _format_filter_label(*, event_type: str, kind: str) -> str:
    filters = []
    if event_type:
        filters.append(f"event type '{event_type}'")
    if kind:
        filters.append(f"kind '{kind}'")
    return " and ".join(filters)
