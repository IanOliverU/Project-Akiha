"""Chat window for the Phase 2 companion foundation."""

from __future__ import annotations

from html import escape

from PySide6.QtCore import Signal
from PySide6.QtGui import QTextCursor
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
    cancel_requested = Signal()

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

        self._stop_button = QPushButton("Stop")
        self._stop_button.setDisabled(True)
        self._stop_button.clicked.connect(self._request_cancel)

        input_layout = QHBoxLayout()
        input_layout.addWidget(self._input)
        input_layout.addWidget(self._send_button)
        input_layout.addWidget(self._stop_button)

        layout = QVBoxLayout()
        layout.addWidget(self._history_view)
        layout.addLayout(input_layout)
        self.setLayout(layout)

    def append_message(self, speaker: str, content: str) -> None:
        """Append a message to the visible transcript."""
        self._history_view.append(f"<b>{escape(speaker)}</b>: {escape(content)}")

    def begin_streaming_message(self, speaker: str) -> None:
        """Start a message that will receive incremental text."""
        self._history_view.append(f"<b>{escape(speaker)}</b>: ")

    def append_stream_delta(self, content: str) -> None:
        """Append incremental plain text to the current message."""
        self._history_view.moveCursor(QTextCursor.MoveOperation.End)
        self._history_view.insertPlainText(content)
        self._history_view.ensureCursorVisible()

    def append_error(self, content: str) -> None:
        """Append an error-style message to the transcript."""
        self._history_view.append(
            f"<span style='color:#b00020'>{escape(content)}</span>"
        )

    def append_notice(self, content: str) -> None:
        """Append a low-emphasis status message to the transcript."""
        self._history_view.append(
            f"<span style='color:#666666'>{escape(content)}</span>"
        )

    def set_busy(self, is_busy: bool) -> None:
        """Toggle input controls while a response is being generated."""
        self._input.setDisabled(is_busy)
        self._send_button.setDisabled(is_busy)
        self._stop_button.setDisabled(not is_busy)

    def _submit_message(self) -> None:
        message = self._input.text().strip()
        if not message:
            return

        self._input.clear()
        self.message_submitted.emit(message)

    def _request_cancel(self) -> None:
        self._stop_button.setDisabled(True)
        self.cancel_requested.emit()
