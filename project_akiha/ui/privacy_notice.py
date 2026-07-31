"""One-time privacy notice for voice and hosted AI processing."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
)


class PrivacyNoticeDialog(QDialog):
    """Explain Project Akiha's local and hosted data boundaries."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Project Akiha Privacy")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setMinimumWidth(480)

        heading = QLabel("Privacy and data")
        heading.setStyleSheet("font-size: 16px; font-weight: 600;")

        summary = QLabel(
            "<p><b>Microphone:</b> Akiha records only after you start "
            "push-to-talk or a microphone test. Raw microphone audio is "
            "temporary and is not retained.</p>"
            "<p><b>Local processing:</b> faster-whisper, VOICEVOX, and Ollama "
            "stay on this PC when selected.</p>"
            "<p><b>Hosted processing:</b> When you select a hosted AI provider, "
            "chat messages and relevant context are sent to that provider. "
            "Subtitles, summaries, and memory extraction may make additional "
            "provider requests.</p>"
            "<p><b>Local storage:</b> Conversations, memories, transcripts, "
            "settings, and logs are stored under your Windows user profile. "
            "Hosted API keys are encrypted for the current Windows user.</p>"
            "<p><b>Assistant actions:</b> Akiha can search approved directories, "
            "navigate their ordinary child folders, open approved folders and "
            "passive files after confirmation, and "
            "launch or gracefully close separately enabled applications. "
            "Application closing sends a normal close request and never "
            "force-terminates a process. She cannot run arbitrary "
            "commands, use AI-supplied paths or arguments, or modify system "
            "files. If AI-assisted proposals are enabled, the selected AI "
            "provider receives the action request. Akiha does not add approved "
            "paths, directory listings, search results, or file contents to "
            "that request.</p>"
            "<p><b>Spotify:</b> Spotify integration is optional and uses a "
            "browser sign-in with PKCE. Search, library, device, and playback "
            "requests are sent directly to Spotify only after you connect. "
            "The refresh token is encrypted for the current Windows user; "
            "personal listening exports stay local and are never packaged.</p>"
        )
        summary.setWordWrap(True)
        summary.setTextFormat(Qt.TextFormat.RichText)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        acknowledge_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        acknowledge_button.setText("I understand")
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout()
        layout.addWidget(heading)
        layout.addWidget(summary)
        layout.addWidget(buttons)
        self.setLayout(layout)
