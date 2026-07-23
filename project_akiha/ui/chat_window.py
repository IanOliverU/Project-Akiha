"""Chat window for the Phase 2 companion foundation."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class ChatWindow(QWidget):
    """Simple chat UI that emits user-submitted messages."""

    message_submitted = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Akiha Chat")
        self.setMinimumSize(420, 520)

        self._history_view = QTextEdit()
        self._history_view.setReadOnly(True)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Message Akiha")
        self._input.returnPressed.connect(self._submit_message)

        self._send_button = QPushButton("Send")
        self._send_button.clicked.connect(self._submit_message)

        input_layout = QHBoxLayout()
        input_layout.addWidget(self._input)
        input_layout.addWidget(self._send_button)

        layout = QVBoxLayout()
        layout.addWidget(self._history_view)
        layout.addLayout(input_layout)
        self.setLayout(layout)

    def append_message(self, speaker: str, content: str) -> None:
        """Append a message to the visible transcript."""
        self._history_view.append(f"<b>{speaker}</b>: {content}")

    def append_error(self, content: str) -> None:
        """Append an error-style message to the transcript."""
        self._history_view.append(f"<span style='color:#b00020'>{content}</span>")

    def set_busy(self, is_busy: bool) -> None:
        """Toggle input controls while a response is being generated."""
        self._input.setDisabled(is_busy)
        self._send_button.setDisabled(is_busy)

    def _submit_message(self) -> None:
        message = self._input.text().strip()
        if not message:
            return

        self._input.clear()
        self.message_submitted.emit(message)
