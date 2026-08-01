"""Chat window for the Phase 2 companion foundation."""

from __future__ import annotations

from html import escape

from PySide6.QtCore import Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
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

from project_akiha.ui.theme import AKIHA_PALETTE, chat_stylesheet


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
        self.setObjectName("akihaChatWindow")
        self.setMinimumSize(480, 540)
        self.resize(580, 660)
        self.setStyleSheet(chat_stylesheet())

        self._history_view = QTextEdit()
        self._history_view.setObjectName("chatHistory")
        self._history_view.setReadOnly(True)
        self._history_view.document().setDefaultStyleSheet(f"""
            .speaker-user {{
                color: {AKIHA_PALETTE.listening};
                font-weight: 700;
            }}
            .speaker-assistant {{
                color: {AKIHA_PALETTE.speaking};
                font-weight: 700;
            }}
            .notice {{ color: {AKIHA_PALETTE.muted_text}; }}
            .proactive-title {{
                color: {AKIHA_PALETTE.highlight};
                font-weight: 700;
            }}
            .proactive-body {{ color: {AKIHA_PALETTE.text}; }}
            .subtitle-label {{
                color: {AKIHA_PALETTE.muted_text};
                font-weight: 600;
            }}
            .subtitle-body {{
                color: {AKIHA_PALETTE.muted_text};
                font-style: italic;
            }}
            .error {{
                color: {AKIHA_PALETTE.error};
                font-weight: 600;
            }}
            """)

        self._new_chat_button = QPushButton("New chat")
        self._new_chat_button.clicked.connect(self.new_chat_requested.emit)

        self._clear_chat_button = QPushButton("Clear chat")
        self._clear_chat_button.clicked.connect(self._request_clear_chat)

        self._export_chat_button = QPushButton("Export")
        self._export_chat_button.clicked.connect(self._request_export_chat)

        self._presence_label = QLabel("Akiha is calm.")
        self._presence_label.setObjectName("chatPresence")
        self._status_label = QLabel("Ready")
        self._status_label.setObjectName("chatStatus")

        self._input = QLineEdit()
        self._input.setObjectName("chatInput")
        self._input.setPlaceholderText("Message Akiha")
        self._input.returnPressed.connect(self._submit_message)

        self._voice_input_status = QLabel("Microphone disabled")
        self._voice_input_status.setObjectName("voiceInputStatus")
        self._voice_input_status.setWordWrap(True)

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
        self._voice_replay_button.setObjectName("replayButton")
        self._voice_replay_button.setFixedSize(34, 34)
        self._voice_replay_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
        )
        self._voice_replay_button.setToolTip("Replay last spoken response")
        self._voice_replay_button.setAccessibleName("Replay voice")
        self._voice_replay_button.clicked.connect(self.voice_replay_requested.emit)
        self._refresh_voice_replay_button()

        self._send_button = QPushButton("Send")
        self._send_button.setObjectName("primaryButton")
        self._send_button.clicked.connect(self._submit_message)

        self._stop_button = QPushButton("Stop")
        self._stop_button.setObjectName("stopButton")
        self._stop_button.setDisabled(True)
        self._stop_button.clicked.connect(self._request_cancel)

        action_layout = QHBoxLayout()
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(8)
        action_layout.addWidget(self._new_chat_button)
        action_layout.addWidget(self._clear_chat_button)
        action_layout.addWidget(self._export_chat_button)
        action_layout.addStretch(1)

        presence_layout = QHBoxLayout()
        presence_layout.setContentsMargins(0, 0, 0, 0)
        presence_layout.addWidget(self._presence_label)
        presence_layout.addStretch(1)
        presence_layout.addWidget(self._status_label)

        toolbar = QFrame()
        toolbar.setObjectName("chatToolbar")
        toolbar_layout = QVBoxLayout()
        toolbar_layout.setContentsMargins(12, 10, 12, 10)
        toolbar_layout.setSpacing(8)
        toolbar_layout.addLayout(action_layout)
        toolbar_layout.addLayout(presence_layout)
        toolbar.setLayout(toolbar_layout)

        input_layout = QHBoxLayout()
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(8)
        input_layout.addWidget(self._input)
        input_layout.addWidget(self._voice_button)
        input_layout.addWidget(self._voice_replay_button)
        input_layout.addWidget(self._send_button)
        input_layout.addWidget(self._stop_button)

        composer = QFrame()
        composer.setObjectName("chatComposer")
        composer_layout = QVBoxLayout()
        composer_layout.setContentsMargins(12, 10, 12, 12)
        composer_layout.setSpacing(8)
        composer_layout.addWidget(self._voice_input_status)
        composer_layout.addLayout(input_layout)
        composer.setLayout(composer_layout)

        layout = QVBoxLayout()
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)
        layout.addWidget(toolbar)
        layout.addWidget(self._history_view, stretch=1)
        layout.addWidget(composer)
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

    def append_assistant_translation(self, content: str) -> None:
        """Append a non-canonical English subtitle below an assistant reply."""
        translation = content.strip()
        if not translation:
            return
        self._history_view.append(
            '<span class="subtitle-label">English</span>: '
            f'<span class="subtitle-body">{escape(translation)}</span>'
        )

    def append_translation_unavailable(self) -> None:
        """Show a quiet fallback while preserving the Japanese response."""
        self._history_view.append(
            '<span class="notice">English subtitle unavailable.</span>'
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
        if self._voice_state == "idle" and self._voice_input_enabled:
            self.voice_listen_requested.emit()
        elif self._voice_state == "listening" and self._voice_operation == "input":
            self.voice_listen_stop_requested.emit()
        elif self._voice_state == "thinking":
            if self._voice_operation == "input":
                self.voice_listen_cancel_requested.emit()
            elif self._voice_operation == "output":
                if self._voice_input_enabled:
                    self.voice_listen_requested.emit()
                else:
                    self.voice_speak_stop_requested.emit()
        elif self._voice_state == "speaking" and self._voice_operation == "output":
            if self._voice_input_enabled:
                self.voice_listen_requested.emit()
            else:
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
                if self._voice_input_enabled:
                    label = "Talk"
                    tooltip = "Interrupt and talk"
                    enabled = True
                else:
                    tooltip = "Cancel speech synthesis"
                    enabled = self._voice_output_enabled
        elif self._voice_state == "speaking":
            if self._voice_input_enabled:
                label = "Talk"
                tooltip = "Interrupt and talk"
                enabled = True
            else:
                label = "Stop voice"
                tooltip = "Stop speech playback"
                enabled = self._voice_output_enabled
        elif self._voice_state == "error":
            label = "Voice error"
            tooltip = "Voice needs attention"

        self._voice_button.setText(label)
        self._voice_button.setToolTip(tooltip)
        self._voice_button.setEnabled(enabled)

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
