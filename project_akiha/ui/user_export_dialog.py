"""Trusted-local explicit record selection; no destination or data from providers."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QVBoxLayout,
)

from project_akiha.ui.components import PageHeader
from project_akiha.ui.theme import native_surface_stylesheet


class UserExportDialog(QDialog):
    def __init__(self, catalog, parent=None):
        super().__init__(parent)
        self._catalog = catalog
        self.setStyleSheet(native_surface_stylesheet())
        self.setWindowTitle("Select private records to export")
        self.resize(600, 420)
        layout = QVBoxLayout(self)
        layout.addWidget(
            PageHeader(
                "Export selected records",
                "1 · Select records    2 · Choose a new file    3 · Confirm locally",
            )
        )
        text = QLabel(
            "Choose up to 100 records. Only selected "
            "conversation text or active memories will be "
            "exported. Credentials, settings, logs, "
            "notifications, embeddings and voice references "
            "are excluded. No import or restore is provided."
        )
        text.setWordWrap(True)
        layout.addWidget(text)
        self.kind = QComboBox()
        self.kind.addItems(["conversations", "memories"])
        layout.addWidget(self.kind)
        self.records = QListWidget()
        self.records.setAccessibleName("Records to include in this export")
        layout.addWidget(self.records)
        self.status = QLabel()
        layout.addWidget(self.status)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept_selection)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.kind.currentTextChanged.connect(self._refresh)
        self._refresh()

    def _refresh(self):
        self.records.clear()
        rows = self._catalog.get(self.kind.currentText(), ())
        for identifier, title in rows:
            self.records.addItem(title)
            item = self.records.item(self.records.count() - 1)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, identifier)
        self.status.setText(
            "Select records explicitly; none are selected by "
            "default. Showing at most 1,000 recent records."
        )

    def selection(self):
        return tuple(
            self.records.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.records.count())
            if self.records.item(i).checkState() == Qt.CheckState.Checked
        )

    def _accept_selection(self):
        if not 1 <= len(self.selection()) <= 100:
            self.status.setText("Select 1 to 100 records before continuing.")
            return
        self.accept()
