"""Presentation window for bounded search results and assistant-action audits."""

from __future__ import annotations

import json

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from project_akiha.core.actions import (
    ActionAuditEntry,
    DirectorySearchMatch,
    FileSearchMatch,
)
from project_akiha.ui.fluent_icons import FluentComboBox, fluent_icon
from project_akiha.ui.manager_presentation import (
    ITEM_ACCENT_ROLE,
    ITEM_META_ROLE,
    ITEM_STATUS_ROLE,
    ITEM_TITLE_ROLE,
    ActionItemDelegate,
    TechnicalDetailsHighlighter,
)
from project_akiha.ui.theme import AKIHA_PALETTE, action_history_stylesheet

SearchMatch = FileSearchMatch | DirectorySearchMatch


class AssistantActionHistoryWindow(QWidget):
    """Show bounded search results and sanitized assistant-action history."""

    refresh_requested = Signal()
    clear_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Akiha Assistant Actions")
        self.setObjectName("akihaAssistantActionHistoryWindow")
        self.setMinimumSize(780, 520)
        self.resize(1000, 680)
        self.setStyleSheet(action_history_stylesheet())

        self._audits: tuple[ActionAuditEntry, ...] = ()
        self._search_matches: tuple[SearchMatch, ...] = ()

        self._status_label = QLabel("No assistant actions recorded.")
        self._status_label.setObjectName("actionHistoryStatus")

        self._tabs = QTabBar()
        self._tabs.setObjectName("managerTabs")
        self._tabs.setDocumentMode(True)
        self._tabs.setExpanding(True)
        self._tabs.setUsesScrollButtons(False)
        self._tabs.addTab("Latest search")
        self._tabs.addTab("Audit history")

        self._navigation_stack = QStackedWidget()
        self._navigation_stack.addWidget(self._build_search_navigation())
        self._navigation_stack.addWidget(self._build_audit_navigation())
        self._details_stack = QStackedWidget()
        self._details_stack.addWidget(self._build_search_details_pane())
        self._details_stack.addWidget(self._build_audit_details_pane())
        self._tabs.currentChanged.connect(self._switch_action_tab)
        self._tabs.setCurrentIndex(1)
        self._switch_action_tab(1)

        navigation_layout = QVBoxLayout()
        navigation_layout.setContentsMargins(14, 12, 14, 14)
        navigation_layout.setSpacing(10)
        navigation_layout.addWidget(self._tabs)
        navigation_layout.addWidget(self._navigation_stack, 1)
        navigation_pane = QFrame()
        navigation_pane.setObjectName("managerNavigationPane")
        navigation_pane.setFixedWidth(360)
        navigation_pane.setLayout(navigation_layout)
        self._navigation_pane = navigation_pane

        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        body_layout.addWidget(navigation_pane)
        body_layout.addWidget(self._details_stack, 1)
        body = QFrame()
        body.setObjectName("managerBody")
        body.setLayout(body_layout)
        self._body = body

        refresh_button = QPushButton("Refresh")
        refresh_button.setObjectName("primaryButton")
        refresh_button.setIcon(fluent_icon("\ue72c"))
        refresh_button.clicked.connect(self.refresh_requested.emit)
        clear_button = QPushButton("Clear history")
        clear_button.setIcon(fluent_icon("\ue74d"))
        clear_button.clicked.connect(self._request_clear_history)

        button_layout = QHBoxLayout()
        button_layout.addWidget(clear_button)
        button_layout.addStretch(1)
        button_layout.addWidget(refresh_button)

        icon_label = QLabel()
        icon_label.setPixmap(fluent_icon("\ue756", 20).pixmap(22, 22))
        title_label = QLabel("Akiha Assistant Actions")
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
        layout.addWidget(body, 1)
        layout.addWidget(footer)
        self.setLayout(layout)

    def _request_clear_history(self) -> None:
        answer = QMessageBox.question(
            self,
            "Clear assistant action history",
            "Delete all sanitized assistant-action history?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.clear_requested.emit()

    def update_search_results(
        self,
        matches: tuple[SearchMatch, ...],
        *,
        summary: str = "",
    ) -> None:
        """Replace the visible search result metadata."""
        self._search_matches = matches
        self._search_list.clear()
        for match in matches:
            item = QListWidgetItem(_format_match_summary(match))
            item.setData(Qt.ItemDataRole.UserRole, match.path)
            item.setData(ITEM_TITLE_ROLE, match.name)
            item.setData(ITEM_META_ROLE, _format_match_metadata(match))
            item.setData(ITEM_ACCENT_ROLE, AKIHA_PALETTE.highlight)
            item.setData(ITEM_STATUS_ROLE, "result")
            self._search_list.addItem(item)

        self._search_status.setText(summary or _format_search_count(len(matches)))
        if matches:
            self._search_list.setCurrentRow(0)
        else:
            self._search_list.setCurrentRow(-1)
            self._clear_search_details()

    def update_audits(self, audits: tuple[ActionAuditEntry, ...]) -> None:
        """Replace the audit history and preserve compatible filters."""
        selected_status = self._selected_status_filter()
        self._audits = audits
        self._audit_list.clear()
        self._replace_status_options(selected_status)

        for audit in audits:
            item = QListWidgetItem(_format_audit_summary(audit))
            item.setData(Qt.ItemDataRole.UserRole, audit.id)
            item.setData(Qt.ItemDataRole.UserRole + 1, _audit_search_text(audit))
            item.setData(ITEM_TITLE_ROLE, audit.action_id)
            item.setData(ITEM_META_ROLE, _format_audit_metadata(audit))
            item.setData(ITEM_ACCENT_ROLE, _audit_accent(audit))
            item.setData(ITEM_STATUS_ROLE, audit.result_status.value)
            self._audit_list.addItem(item)

        self._apply_audit_filter()
        first_visible = self._first_visible_row(self._audit_list)
        self._audit_list.setCurrentRow(
            first_visible if first_visible is not None else -1
        )

    def append_notice(self, message: str) -> None:
        """Show a short status message without changing persisted history."""
        self._status_label.setText(message)

    def _build_search_navigation(self) -> QWidget:
        self._search_status = QLabel("No search results.")
        self._search_status.setObjectName("managerSectionLabel")
        self._search_list = QListWidget()
        self._search_list.setObjectName("actionRecordList")
        self._search_list.setItemDelegate(ActionItemDelegate(self._search_list))
        self._search_list.currentItemChanged.connect(self._show_search_details)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self._search_status)
        layout.addWidget(self._search_list, 1)
        tab = QWidget()
        tab.setLayout(layout)
        return tab

    def _build_audit_navigation(self) -> QWidget:
        self._audit_filter = QLineEdit()
        self._audit_filter.setObjectName("managerSearchInput")
        self._audit_filter.setPlaceholderText("Filter action history")
        self._audit_filter.addAction(
            fluent_icon("\ue721"),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self._audit_filter.textChanged.connect(self._apply_audit_filter)

        self._audit_status_filter = FluentComboBox()
        self._audit_status_filter.setFixedWidth(110)
        self._audit_status_filter.currentTextChanged.connect(self._apply_audit_filter)
        self._replace_status_options("")

        self._audit_list = QListWidget()
        self._audit_list.setObjectName("actionRecordList")
        self._audit_list.setItemDelegate(ActionItemDelegate(self._audit_list))
        self._audit_list.currentItemChanged.connect(self._show_audit_details)

        filter_layout = QHBoxLayout()
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.setSpacing(8)
        filter_layout.addWidget(self._audit_filter)
        filter_layout.addWidget(self._audit_status_filter)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addLayout(filter_layout)
        layout.addWidget(self._audit_list, 1)
        tab = QWidget()
        tab.setLayout(layout)
        return tab

    def _build_search_details_pane(self) -> QWidget:
        self._search_detail_title = QLabel("Search Result Metadata")
        self._search_detail_title.setObjectName("managerDetailTitle")
        subtitle = QLabel("Bounded metadata for the selected search result.")
        subtitle.setObjectName("managerDetailMeta")
        self._search_status_badge = QLabel("RESULT")
        self._search_status_badge.setObjectName("statusBadge")
        self._search_status_badge.setProperty("semantic", "neutral")

        header = _detail_header(
            self._search_detail_title,
            subtitle,
            self._search_status_badge,
        )
        self._search_fields, fields_widget = _metadata_grid(
            ("Name", "Type", "Path", "Modified", "Size")
        )
        self._search_details = QPlainTextEdit()
        self._search_details.setObjectName("managerCodeBlock")
        self._search_details.setReadOnly(True)
        self._search_details.setPlaceholderText(
            "Select a result to inspect bounded metadata."
        )
        self._search_details_highlighter = TechnicalDetailsHighlighter(
            self._search_details.document()
        )

        section_label = QLabel("BOUNDED METADATA")
        section_label.setObjectName("managerSectionLabel")
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header)
        layout.addWidget(fields_widget)
        layout.addWidget(section_label)
        layout.addWidget(self._search_details, 1)
        pane = QFrame()
        pane.setObjectName("managerDetailPane")
        pane.setLayout(layout)
        return pane

    def _build_audit_details_pane(self) -> QWidget:
        title = QLabel("Action Metadata")
        title.setObjectName("managerDetailTitle")
        subtitle = QLabel("Detailed execution telemetry for selected audit entry.")
        subtitle.setObjectName("managerDetailMeta")
        self._audit_status_badge = QLabel("NO SELECTION")
        self._audit_status_badge.setObjectName("statusBadge")
        self._audit_status_badge.setProperty("semantic", "neutral")

        header = _detail_header(title, subtitle, self._audit_status_badge)
        self._audit_fields, fields_widget = _metadata_grid(
            ("ID", "Created", "Action", "Source", "Target", "Permission", "Duration")
        )
        self._audit_details = QPlainTextEdit()
        self._audit_details.setObjectName("managerCodeBlock")
        self._audit_details.setReadOnly(True)
        self._audit_details.setPlaceholderText(
            "Select an audit entry to inspect its sanitized execution record."
        )
        self._audit_details_highlighter = TechnicalDetailsHighlighter(
            self._audit_details.document()
        )

        section_label = QLabel("EXECUTION PAYLOAD")
        section_label.setObjectName("managerSectionLabel")
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header)
        layout.addWidget(fields_widget)
        layout.addWidget(section_label)
        layout.addWidget(self._audit_details, 1)
        pane = QFrame()
        pane.setObjectName("managerDetailPane")
        pane.setLayout(layout)
        return pane

    def _switch_action_tab(self, index: int) -> None:
        self._navigation_stack.setCurrentIndex(index)
        self._details_stack.setCurrentIndex(index)

    def _show_search_details(
        self,
        current: QListWidgetItem | None,
        previous: QListWidgetItem | None,
    ) -> None:
        del previous
        match = self._match_for_item(current)
        if match is None:
            self._clear_search_details()
            return
        match_type = "Directory" if isinstance(match, DirectorySearchMatch) else "File"
        self._search_fields["Name"].setText(match.name)
        self._search_fields["Type"].setText(match_type)
        self._search_fields["Path"].setText(match.path)
        self._search_fields["Modified"].setText(match.modified_at)
        self._search_fields["Size"].setText(
            "Not applicable"
            if isinstance(match, DirectorySearchMatch)
            else f"{match.size_bytes:,} bytes"
        )
        self._search_status_badge.setText(match_type.upper())
        _set_semantic(self._search_status_badge, "neutral")
        self._search_details.setPlainText(_format_match_details(match))

    def _show_audit_details(
        self,
        current: QListWidgetItem | None,
        previous: QListWidgetItem | None,
    ) -> None:
        del previous
        audit = self._audit_for_item(current)
        if audit is None:
            self._clear_audit_details()
            return
        target = audit.normalized_target or "None"
        self._audit_fields["ID"].setText(f"#{audit.id}")
        self._audit_fields["Created"].setText(audit.created_at)
        self._audit_fields["Action"].setText(audit.action_id)
        self._audit_fields["Source"].setText(audit.source)
        self._audit_fields["Target"].setText(target)
        self._audit_fields["Permission"].setText(
            audit.permission_decision.value.upper()
        )
        self._audit_fields["Duration"].setText(f"{audit.duration_ms} ms")
        status = audit.result_status.value
        self._audit_status_badge.setText(status.upper())
        _set_semantic(self._audit_status_badge, _status_semantic(status))
        self._audit_details.setPlainText(_format_audit_details(audit))

    def _clear_search_details(self) -> None:
        for label in self._search_fields.values():
            label.setText("-")
        self._search_status_badge.setText("NO SELECTION")
        _set_semantic(self._search_status_badge, "neutral")
        self._search_details.clear()

    def _clear_audit_details(self) -> None:
        for label in self._audit_fields.values():
            label.setText("-")
        self._audit_status_badge.setText("NO SELECTION")
        _set_semantic(self._audit_status_badge, "neutral")
        self._audit_details.clear()

    def _apply_audit_filter(self) -> None:
        query = self._audit_filter.text().strip().casefold()
        status_filter = self._selected_status_filter()
        visible_count = 0
        for index in range(self._audit_list.count()):
            item = self._audit_list.item(index)
            audit = self._audit_for_item(item)
            search_text = str(item.data(Qt.ItemDataRole.UserRole + 1)).casefold()
            visible = bool(
                audit is not None
                and (not query or query in search_text)
                and (not status_filter or audit.result_status.value == status_filter)
            )
            item.setHidden(not visible)
            if visible:
                visible_count += 1

        current = self._audit_list.currentItem()
        if current is not None and current.isHidden():
            first_visible = self._first_visible_row(self._audit_list)
            self._audit_list.setCurrentRow(
                first_visible if first_visible is not None else -1
            )
        if visible_count == 0:
            self._clear_audit_details()
        self._status_label.setText(
            _format_audit_count(visible_count, len(self._audits))
        )

    def _replace_status_options(self, selected_status: str) -> None:
        if not hasattr(self, "_audit_status_filter"):
            return
        values = sorted({audit.result_status.value for audit in self._audits})
        self._audit_status_filter.blockSignals(True)
        self._audit_status_filter.clear()
        self._audit_status_filter.addItem("Status", "")
        for value in values:
            self._audit_status_filter.addItem(value, value)
        if selected_status:
            index = self._audit_status_filter.findData(selected_status)
            if index >= 0:
                self._audit_status_filter.setCurrentIndex(index)
        self._audit_status_filter.blockSignals(False)

    def _selected_status_filter(self) -> str:
        if not hasattr(self, "_audit_status_filter"):
            return ""
        value = self._audit_status_filter.currentData()
        return str(value) if value is not None else ""

    def _match_for_item(self, item: QListWidgetItem | None) -> SearchMatch | None:
        if item is None:
            return None
        path = item.data(Qt.ItemDataRole.UserRole)
        return next(
            (match for match in self._search_matches if match.path == path), None
        )

    def _audit_for_item(self, item: QListWidgetItem | None) -> ActionAuditEntry | None:
        if item is None:
            return None
        audit_id = item.data(Qt.ItemDataRole.UserRole)
        return next((audit for audit in self._audits if audit.id == audit_id), None)

    @staticmethod
    def _first_visible_row(list_widget: QListWidget) -> int | None:
        for index in range(list_widget.count()):
            if not list_widget.item(index).isHidden():
                return index
        return None


def _format_match_summary(match: SearchMatch) -> str:
    if isinstance(match, DirectorySearchMatch):
        return f"{match.name}  (directory)"
    return f"{match.name}  ({match.size_bytes:,} bytes)"


def _format_match_details(match: SearchMatch | None) -> str:
    if match is None:
        return ""
    if isinstance(match, DirectorySearchMatch):
        return "\n".join(
            (
                f"Name: {match.name}",
                f"Path: {match.path}",
                "Type: Directory",
                f"Modified: {match.modified_at}",
            )
        )
    return "\n".join(
        (
            f"Name: {match.name}",
            f"Path: {match.path}",
            f"Size: {match.size_bytes:,} bytes",
            f"Modified: {match.modified_at}",
        )
    )


def _format_match_metadata(match: SearchMatch) -> str:
    if isinstance(match, DirectorySearchMatch):
        return "DIR"
    return "FILE"


def _format_search_count(count: int) -> str:
    noun = "result" if count == 1 else "results"
    return f"{count} search {noun}"


def _format_audit_summary(audit: ActionAuditEntry) -> str:
    return (
        f"#{audit.id}  {audit.created_at}  "
        f"{audit.action_id}  {audit.result_status.value}"
    )


def _format_audit_details(audit: ActionAuditEntry | None) -> str:
    if audit is None:
        return ""
    failure = audit.failure_category.value if audit.failure_category else "None"
    return json.dumps(
        {
            "correlation_id": audit.correlation_id,
            "result": audit.result_status.value,
            "failure": failure,
        },
        indent=2,
    )


def _format_audit_metadata(audit: ActionAuditEntry) -> str:
    return (
        f"#{audit.id}  ·  {audit.created_at}  ·  "
        f"{audit.result_status.value.upper()}"
    )


def _audit_accent(audit: ActionAuditEntry) -> str:
    status = audit.result_status.value.casefold()
    if status == "success":
        return AKIHA_PALETTE.success
    if status in {"denied", "failed", "unavailable", "timed_out"}:
        return AKIHA_PALETTE.error
    if status in {"confirmation_required", "cancelled"}:
        return "#E0C561"
    return AKIHA_PALETTE.highlight


def _detail_header(title: QLabel, subtitle: QLabel, badge: QLabel) -> QFrame:
    heading = QVBoxLayout()
    heading.setContentsMargins(0, 0, 0, 0)
    heading.setSpacing(4)
    heading.addWidget(title)
    heading.addWidget(subtitle)

    layout = QHBoxLayout()
    layout.setContentsMargins(24, 20, 24, 18)
    layout.addLayout(heading)
    layout.addStretch(1)
    layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
    frame = QFrame()
    frame.setObjectName("managerDetailHeader")
    frame.setLayout(layout)
    return frame


def _metadata_grid(labels: tuple[str, ...]) -> tuple[dict[str, QLabel], QFrame]:
    values: dict[str, QLabel] = {}
    grid = QGridLayout()
    grid.setContentsMargins(24, 18, 24, 22)
    grid.setHorizontalSpacing(28)
    grid.setVerticalSpacing(16)
    for index, label_text in enumerate(labels):
        label = QLabel(label_text.upper())
        label.setObjectName("managerFieldLabel")
        value = QLabel("-")
        value.setObjectName("managerValueChip")
        value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        value.setWordWrap(True)
        values[label_text] = value

        field_layout = QVBoxLayout()
        field_layout.setContentsMargins(0, 0, 0, 0)
        field_layout.setSpacing(6)
        field_layout.addWidget(label)
        field_layout.addWidget(value)
        field_layout.addStretch(1)
        field = QWidget()
        field.setLayout(field_layout)
        grid.addWidget(field, index // 2, index % 2)

    frame = QFrame()
    frame.setObjectName("managerMetadataGrid")
    frame.setLayout(grid)
    return values, frame


def _set_semantic(label: QLabel, semantic: str) -> None:
    label.setProperty("semantic", semantic)
    label.style().unpolish(label)
    label.style().polish(label)


def _status_semantic(status: str) -> str:
    normalized = status.casefold()
    if normalized == "success":
        return "success"
    if normalized in {"denied", "failed", "unavailable", "timed_out"}:
        return "error"
    if normalized in {"confirmation_required", "cancelled"}:
        return "warning"
    return "neutral"


def _audit_search_text(audit: ActionAuditEntry) -> str:
    return " ".join(
        (
            str(audit.id),
            audit.created_at,
            audit.action_id,
            audit.source,
            audit.normalized_target or "",
            audit.permission_decision.value,
            audit.result_status.value,
            audit.failure_category.value if audit.failure_category else "",
        )
    )


def _format_audit_count(visible_count: int, total_count: int) -> str:
    noun = "entry" if total_count == 1 else "entries"
    if visible_count == total_count:
        return f"{total_count} audit {noun}"
    return f"{visible_count} of {total_count} audit {noun}"
