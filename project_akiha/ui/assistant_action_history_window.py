"""Presentation window for bounded search results and assistant-action audits."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from project_akiha.core.actions import (
    ActionAuditEntry,
    DirectorySearchMatch,
    FileSearchMatch,
)
from project_akiha.ui.theme import action_history_stylesheet

SearchMatch = FileSearchMatch | DirectorySearchMatch


class AssistantActionHistoryWindow(QWidget):
    """Show bounded search results and sanitized assistant-action history."""

    refresh_requested = Signal()
    clear_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Akiha Assistant Actions")
        self.setObjectName("akihaAssistantActionHistoryWindow")
        self.setMinimumSize(720, 480)
        self.resize(820, 580)
        self.setStyleSheet(action_history_stylesheet())

        self._audits: tuple[ActionAuditEntry, ...] = ()
        self._search_matches: tuple[SearchMatch, ...] = ()

        self._status_label = QLabel("No assistant actions recorded.")
        self._status_label.setObjectName("actionHistoryStatus")

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_search_tab(), "Latest search")
        self._tabs.addTab(self._build_audit_tab(), "Audit history")

        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh_requested.emit)
        clear_button = QPushButton("Clear history")
        clear_button.clicked.connect(self._request_clear_history)

        button_layout = QHBoxLayout()
        button_layout.addWidget(refresh_button)
        button_layout.addWidget(clear_button)
        button_layout.addStretch()

        layout = QVBoxLayout()
        layout.addWidget(self._status_label)
        layout.addWidget(self._tabs)
        layout.addLayout(button_layout)
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
            self._search_list.addItem(item)

        self._search_status.setText(summary or _format_search_count(len(matches)))
        if matches:
            self._search_list.setCurrentRow(0)
        else:
            self._search_list.setCurrentRow(-1)
            self._search_details.clear()

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
            self._audit_list.addItem(item)

        self._apply_audit_filter()
        first_visible = self._first_visible_row(self._audit_list)
        self._audit_list.setCurrentRow(
            first_visible if first_visible is not None else -1
        )

    def append_notice(self, message: str) -> None:
        """Show a short status message without changing persisted history."""
        self._status_label.setText(message)

    def _build_search_tab(self) -> QWidget:
        self._search_status = QLabel("No search results.")
        self._search_list = QListWidget()
        self._search_list.currentItemChanged.connect(self._show_search_details)
        self._search_details = QPlainTextEdit()
        self._search_details.setReadOnly(True)
        self._search_details.setPlaceholderText("Select a result to inspect metadata.")

        splitter = QSplitter()
        splitter.addWidget(self._search_list)
        splitter.addWidget(self._search_details)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)

        layout = QVBoxLayout()
        layout.addWidget(self._search_status)
        layout.addWidget(splitter)
        tab = QWidget()
        tab.setLayout(layout)
        return tab

    def _build_audit_tab(self) -> QWidget:
        self._audit_filter = QLineEdit()
        self._audit_filter.setPlaceholderText("Filter action history")
        self._audit_filter.textChanged.connect(self._apply_audit_filter)

        self._audit_status_filter = QComboBox()
        self._audit_status_filter.currentTextChanged.connect(self._apply_audit_filter)
        self._replace_status_options("")

        self._audit_list = QListWidget()
        self._audit_list.currentItemChanged.connect(self._show_audit_details)
        self._audit_details = QPlainTextEdit()
        self._audit_details.setReadOnly(True)
        self._audit_details.setPlaceholderText(
            "Select an audit entry to inspect details."
        )

        filter_layout = QHBoxLayout()
        filter_layout.addWidget(self._audit_filter)
        filter_layout.addWidget(self._audit_status_filter)

        splitter = QSplitter()
        splitter.addWidget(self._audit_list)
        splitter.addWidget(self._audit_details)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)

        layout = QVBoxLayout()
        layout.addLayout(filter_layout)
        layout.addWidget(splitter)
        tab = QWidget()
        tab.setLayout(layout)
        return tab

    def _show_search_details(
        self,
        current: QListWidgetItem | None,
        previous: QListWidgetItem | None,
    ) -> None:
        del previous
        match = self._match_for_item(current)
        self._search_details.setPlainText(
            _format_match_details(match) if match is not None else ""
        )

    def _show_audit_details(
        self,
        current: QListWidgetItem | None,
        previous: QListWidgetItem | None,
    ) -> None:
        del previous
        audit = self._audit_for_item(current)
        self._audit_details.setPlainText(
            _format_audit_details(audit) if audit is not None else ""
        )

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
            self._audit_details.clear()
        self._status_label.setText(
            _format_audit_count(visible_count, len(self._audits))
        )

    def _replace_status_options(self, selected_status: str) -> None:
        if not hasattr(self, "_audit_status_filter"):
            return
        values = sorted({audit.result_status.value for audit in self._audits})
        self._audit_status_filter.blockSignals(True)
        self._audit_status_filter.clear()
        self._audit_status_filter.addItem("All statuses", "")
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
    target = audit.normalized_target or "None"
    failure = audit.failure_category.value if audit.failure_category else "None"
    return "\n".join(
        (
            f"ID: {audit.id}",
            f"Created: {audit.created_at}",
            f"Action: {audit.action_id}",
            f"Source: {audit.source}",
            f"Target: {target}",
            f"Permission: {audit.permission_decision.value}",
            f"Result: {audit.result_status.value}",
            f"Duration: {audit.duration_ms} ms",
            f"Failure: {failure}",
        )
    )


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
