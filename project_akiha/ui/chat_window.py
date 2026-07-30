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
    QStyle,
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
    voice_listen_requested = Signal()
    voice_listen_stop_requested = Signal()
    voice_listen_cancel_requested = Signal()
    voice_speak_stop_requested = Signal()
    voice_replay_requested = Signal()

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
            .proactive-title { color: #7a2e8f; font-weight: 700; }
            .proactive-body { color: #2f3136; }
            .error { color: #b00020; font-weight: 600; }
            """)

        self._new_chat_button = QPushButton("New chat")
        self._new_chat_button.clicked.connect(self.new_chat_requested.emit)

        self._clear_chat_button = QPushButton("Clear chat")
        self._clear_chat_button.clicked.connect(self._request_clear_chat)

        self._export_chat_button = QPushButton("Export")
        self._export_chat_button.clicked.connect(self._request_export_chat)

        self._presence_label = QLabel("Akiha is calm.")
        self._status_label = QLabel("Ready")

        self._input = QLineEdit()
        self._input.setPlaceholderText("Message Akiha")
        self._input.returnPressed.connect(self._submit_message)

        self._voice_input_status = QLabel("Microphone disabled")
        self._voice_input_status.setWordWrap(True)
        self._voice_input_status.setStyleSheet("color: #666666;")

        self._voice_input_enabled = False
        self._voice_output_enabled = False
        self._voice_state = "muted"
        self._voice_operation = "none"
        self._voice_replay_available = False
        self._chat_busy = False
        self._voice_button = QPushButton("Talk")
        self._voice_button.setFixedWidth(96)
        self._voice_button.setToolTip("Push to talk")
        self._voice_button.clicked.connect(self._request_voice_action)
        self._refresh_voice_button()

        self._voice_replay_button = QPushButton()
        self._voice_replay_button.setFixedSize(34, 34)
        self._voice_replay_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
        )
        self._voice_replay_button.setToolTip("Replay last spoken response")
        self._voice_replay_button.setAccessibleName("Replay voice")
        self._voice_replay_button.clicked.connect(self.voice_replay_requested.emit)
        self._refresh_voice_replay_button()

        self._send_button = QPushButton("Send")
        self._send_button.clicked.connect(self._submit_message)

        self._stop_button = QPushButton("Stop")
        self._stop_button.setDisabled(True)
        self._stop_button.clicked.connect(self._request_cancel)

        toolbar_layout = QHBoxLayout()
        toolbar_layout.addWidget(self._new_chat_button)
        toolbar_layout.addWidget(self._clear_chat_button)
        toolbar_layout.addWidget(self._export_chat_button)
        toolbar_layout.addWidget(self._presence_label)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(self._status_label)

        input_layout = QHBoxLayout()
        input_layout.addWidget(self._input)
        input_layout.addWidget(self._voice_button)
        input_layout.addWidget(self._voice_replay_button)
        input_layout.addWidget(self._send_button)
        input_layout.addWidget(self._stop_button)

        layout = QVBoxLayout()
        layout.addLayout(toolbar_layout)
        layout.addWidget(self._history_view)
        layout.addWidget(self._voice_input_status)
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

    def append_proactive_suggestion(self, content: str, kind: str) -> None:
        """Append a proactive companion suggestion to the transcript."""
        title = _proactive_title(kind)
        self._history_view.append(
            f'<span class="proactive-title">{escape(title)}</span>: '
            f'<span class="proactive-body">{escape(content)}</span>'
        )

    def set_status(self, status: str) -> None:
        """Show the current chat status."""
        self._status_label.setText(status)

    def set_presence_text(self, text: str) -> None:
        """Show the current companion presence text."""
        self._presence_label.setText(text.strip() or "Akiha is nearby.")

    def set_voice_capabilities(
        self,
        input_enabled: bool,
        output_enabled: bool,
    ) -> None:
        """Update configured voice input and output availability."""
        self._voice_input_enabled = input_enabled
        self._voice_output_enabled = output_enabled
        self._refresh_voice_button()
        self._refresh_voice_replay_button()

    def set_voice_state(self, state: str, operation: str = "none") -> None:
        """Update the push-to-talk control for a runtime voice state."""
        self._voice_state = state
        self._voice_operation = operation
        self._refresh_voice_button()
        self._refresh_voice_replay_button()

    def set_voice_replay_available(self, available: bool) -> None:
        """Enable replay after at least one speech request reaches playback."""
        self._voice_replay_available = available
        self._refresh_voice_replay_button()

    def insert_voice_transcript(self, text: str) -> None:
        """Insert recognized text at the input cursor without sending it."""
        transcript = text.strip()
        if not transcript:
            return

        existing = self._input.text()
        cursor_position = self._input.cursorPosition()
        prefix = (
            " "
            if cursor_position > 0 and not existing[cursor_position - 1].isspace()
            else ""
        )
        suffix = (
            " "
            if cursor_position < len(existing)
            and not existing[cursor_position].isspace()
            else ""
        )
        self._input.insert(f"{prefix}{transcript}{suffix}")
        self._input.setFocus()

    def submit_voice_transcript(self, text: str) -> None:
        """Insert and submit a final recognized utterance."""
        if self._chat_busy:
            return
        self.insert_voice_transcript(text)
        self._submit_message()

    def set_voice_input_status(self, status: str) -> None:
        """Show a non-persistent microphone or transcription status."""
        self._voice_input_status.setText(status.strip() or "Microphone ready")

    def show_voice_transcript_preview(self, text: str) -> None:
        """Show recognized speech separately from persisted chat history."""
        transcript = text.strip()
        if not transcript:
            return
        self._voice_input_status.setText(
            f'Heard: "{transcript}" - review the message below, then Send.'
        )

    def show_live_voice_transcript(self, text: str) -> None:
        """Show revisable speech recognition while recording continues."""
        transcript = text.strip()
        if not transcript:
            return
        self._voice_input_status.setText(f'Hearing: "{transcript}"')

    def set_busy(self, is_busy: bool) -> None:
        """Toggle input controls while a response is being generated."""
        self._chat_busy = is_busy
        self._input.setDisabled(is_busy)
        self._send_button.setDisabled(is_busy)
        self._stop_button.setDisabled(not is_busy)
        self._new_chat_button.setDisabled(is_busy)
        self._clear_chat_button.setDisabled(is_busy)
        self._export_chat_button.setDisabled(is_busy)
        self._refresh_voice_button()
        self._refresh_voice_replay_button()
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

    def _request_voice_action(self) -> None:
        if self._chat_busy:
            return
        if self._voice_state == "idle" and self._voice_input_enabled:
            self.voice_listen_requested.emit()
        elif self._voice_state == "listening" and self._voice_operation == "input":
            self.voice_listen_stop_requested.emit()
        elif self._voice_state == "thinking":
            if self._voice_operation == "input":
                self.voice_listen_cancel_requested.emit()
            elif self._voice_operation == "output":
                self.voice_speak_stop_requested.emit()
        elif self._voice_state == "speaking" and self._voice_operation == "output":
            self.voice_speak_stop_requested.emit()

    def _refresh_voice_button(self) -> None:
        label = "Talk"
        tooltip = "Push to talk"
        enabled = False

        if self._voice_state == "idle":
            enabled = self._voice_input_enabled
        elif self._voice_state == "listening":
            label = "Stop"
            tooltip = "Finish recording"
            enabled = self._voice_input_enabled
        elif self._voice_state == "thinking":
            label = "Cancel"
            if self._voice_operation == "input":
                tooltip = "Cancel transcription"
                enabled = self._voice_input_enabled
            elif self._voice_operation == "output":
                tooltip = "Cancel speech synthesis"
                enabled = self._voice_output_enabled
        elif self._voice_state == "speaking":
            label = "Stop voice"
            tooltip = "Stop speech playback"
            enabled = self._voice_output_enabled
        elif self._voice_state == "error":
            label = "Voice error"
            tooltip = "Voice needs attention"

        self._voice_button.setText(label)
        self._voice_button.setToolTip(tooltip)
        self._voice_button.setEnabled(enabled and not self._chat_busy)

    def _refresh_voice_replay_button(self) -> None:
        enabled = (
            self._voice_replay_available
            and self._voice_output_enabled
            and self._voice_state == "idle"
            and not self._chat_busy
        )
        self._voice_replay_button.setEnabled(enabled)

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


def _proactive_title(kind: str) -> str:
    labels = {
        "idle_check_in": "Akiha check-in",
        "scheduled_check_in": "Akiha scheduled check-in",
    }
    return labels.get(kind, "Akiha suggestion")
