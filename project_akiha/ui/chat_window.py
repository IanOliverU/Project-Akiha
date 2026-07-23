"""Chat window for the Phase 2 companion foundation."""

from __future__ import annotations

from html import escape

from PySide6.QtCore import Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class ChatWindow(QWidget):
    """Simple chat UI that emits user-submitted messages."""

    message_submitted = Signal(str)
    cancel_requested = Signal()
    new_chat_requested = Signal()
    clear_chat_requested = Signal()
    export_chat_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Akiha Chat")
        self.setMinimumSize(420, 520)

        self._history_view = QTextEdit()
        self._history_view.setReadOnly(True)
        self._history_view.document().setDefaultStyleSheet("""
            .speaker-user { color: #175cd3; font-weight: 700; }
            .speaker-assistant { color: #7a2e8f; font-weight: 700; }
            .notice { color: #666666; }
            .error { color: #b00020; font-weight: 600; }
            """)

        self._new_chat_button = QPushButton("New chat")
        self._new_chat_button.clicked.connect(self.new_chat_requested.emit)

        self._clear_chat_button = QPushButton("Clear chat")
        self._clear_chat_button.clicked.connect(self._request_clear_chat)

        self._export_chat_button = QPushButton("Export")
        self._export_chat_button.clicked.connect(self._request_export_chat)

        self._status_label = QLabel("Ready")

        self._input = QLineEdit()
        self._input.setPlaceholderText("Message Akiha")
        self._input.returnPressed.connect(self._submit_message)

        self._send_button = QPushButton("Send")
        self._send_button.clicked.connect(self._submit_message)

        self._stop_button = QPushButton("Stop")
        self._stop_button.setDisabled(True)
        self._stop_button.clicked.connect(self._request_cancel)

        toolbar_layout = QHBoxLayout()
        toolbar_layout.addWidget(self._new_chat_button)
        toolbar_layout.addWidget(self._clear_chat_button)
        toolbar_layout.addWidget(self._export_chat_button)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(self._status_label)

        input_layout = QHBoxLayout()
        input_layout.addWidget(self._input)
        input_layout.addWidget(self._send_button)
        input_layout.addWidget(self._stop_button)

        layout = QVBoxLayout()
        layout.addLayout(toolbar_layout)
        layout.addWidget(self._history_view)
        layout.addLayout(input_layout)
        self.setLayout(layout)

    def clear_history(self) -> None:
        """Clear the visible transcript."""
        self._history_view.clear()

    def append_message(self, speaker: str, content: str) -> None:
        """Append a message to the visible transcript."""
        self._history_view.append(
            f'<span class="{_speaker_class(speaker)}">{escape(speaker)}</span>: '
            f"{escape(content)}"
        )

    def begin_streaming_message(self, speaker: str) -> None:
        """Start a message that will receive incremental text."""
        self._history_view.append(
            f'<span class="{_speaker_class(speaker)}">{escape(speaker)}</span>: '
        )

    def append_stream_delta(self, content: str) -> None:
        """Append incremental plain text to the current message."""
        self._history_view.moveCursor(QTextCursor.MoveOperation.End)
        self._history_view.insertPlainText(content)
        self._history_view.ensureCursorVisible()

    def append_error(self, content: str) -> None:
        """Append an error-style message to the transcript."""
        self._history_view.append(f'<span class="error">{escape(content)}</span>')

    def append_notice(self, content: str) -> None:
        """Append a low-emphasis status message to the transcript."""
        self._history_view.append(f'<span class="notice">{escape(content)}</span>')

    def set_status(self, status: str) -> None:
        """Show the current chat status."""
        self._status_label.setText(status)

    def set_busy(self, is_busy: bool) -> None:
        """Toggle input controls while a response is being generated."""
        self._input.setDisabled(is_busy)
        self._send_button.setDisabled(is_busy)
        self._stop_button.setDisabled(not is_busy)
        self._new_chat_button.setDisabled(is_busy)
        self._clear_chat_button.setDisabled(is_busy)
        self._export_chat_button.setDisabled(is_busy)
        self.set_status("Thinking..." if is_busy else "Ready")

    def _submit_message(self) -> None:
        message = self._input.text().strip()
        if not message:
            return

        self._input.clear()
        self.message_submitted.emit(message)

    def _request_cancel(self) -> None:
        self._stop_button.setDisabled(True)
        self.set_status("Stopping...")
        self.cancel_requested.emit()

    def _request_clear_chat(self) -> None:
        answer = QMessageBox.question(
            self,
            "Clear chat",
            "Clear the current chat transcript?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.clear_chat_requested.emit()

    def _request_export_chat(self) -> None:
        selected_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export chat transcript",
            "akiha-chat.txt",
            "Text files (*.txt);;All files (*)",
        )
        if selected_path:
            self.export_chat_requested.emit(selected_path)


def _speaker_class(speaker: str) -> str:
    if speaker == "You":
        return "speaker-user"
    return "speaker-assistant"
