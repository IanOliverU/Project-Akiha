"""Shared native presentation components; no domain or persistence authority."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QFrame, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout


class MultilineComposer(QPlainTextEdit):
    """Native multiline editor with compatibility for existing composer routing."""

    returnPressed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAccessibleName("Message Akiha")
        self.setTabChangesFocus(True)
        self.setMinimumHeight(76)
        self.setMaximumHeight(144)
        self.setToolTip("Enter to send · Shift+Enter for a new line")

    def keyPressEvent(self, event: QKeyEvent):
        if (
            event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            self.returnPressed.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def text(self):
        return self.toPlainText()

    def setText(self, value):
        self.setPlainText(value)

    def cursorPosition(self):
        return self.textCursor().position()

    def setCursorPosition(self, position):
        cursor = self.textCursor()
        cursor.setPosition(position)
        self.setTextCursor(cursor)

    def insert(self, value):
        self.insertPlainText(value)


class PageHeader(QFrame):
    def __init__(self, title, description="", parent=None):
        super().__init__(parent)
        self.setObjectName("pageHeader")
        layout = QVBoxLayout(self)
        heading = QLabel(title)
        heading.setObjectName("pageHeading")
        layout.addWidget(heading)
        if description:
            detail = QLabel(description)
            detail.setWordWrap(True)
            detail.setObjectName("secondaryText")
            layout.addWidget(detail)


class NavigationItem(QPushButton):
    def __init__(self, title, icon, parent=None):
        super().__init__(title, parent)
        self.setObjectName("navigationItem")
        self.setAccessibleName(title)
        self.setIcon(icon)
        self.setMinimumHeight(40)
        self.setCheckable(True)


class StatusBadge(QLabel):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setObjectName("statusBadge")
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setWordWrap(True)
