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
            "<p><b>Local processing:</b> faster-whisper, GPT-SoVITS, and Ollama "
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
            "<p><b>External awareness:</b> Gmail and Discord integrations are "
            "optional and read-only. Gmail uses metadata-only access and may "
            "read message IDs, sender, subject, labels, and timestamps, but not "
            "message bodies or attachments. Discord uses an official bot context "
            "and can see only DMs to that bot, mentions of it, and explicitly "
            "approved channels. Akiha cannot inspect your private Discord account, "
            "friends list, personal DMs, or friend requests.</p>"
            "<p><b>External storage:</b> OAuth and bot credentials are encrypted "
            "for the current Windows user. Local synchronization stores only "
            "hashed identifiers, cursors, classifications, timestamps, and "
            "notification status. Message bodies, attachments, raw provider "
            "responses, and credentials are excluded from events and logs.</p>"
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


class HostedLivePrivacyNoticeDialog(QDialog):
    """Require explicit consent before microphone audio may leave the PC."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Gemini Live Cloud Audio")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setMinimumWidth(520)

        heading = QLabel("Before using Gemini Live")
        heading.setStyleSheet("font-size: 16px; font-weight: 600;")

        summary = QLabel(
            "<p><b>Cloud audio:</b> During a Gemini Live conversation, "
            "microphone audio and active conversation context are sent to "
            "Google for off-device processing. Streaming begins only after "
            "you explicitly start that session and stops when you end it, "
            "it fails, or its time limit is reached.</p>"
            "<p><b>Local retention:</b> Akiha keeps raw audio in memory only "
            "for the active operation. Interim transcripts are not saved. "
            "Accepted final conversation text follows Akiha's normal local "
            "chat and memory policy.</p>"
            "<p><b>Google data use:</b> Google's current Gemini API pricing "
            "page states that free-tier content may be used to improve its "
            "products, while paid-tier content is not. Confirm your account "
            "tier and Google's current terms before speaking sensitive "
            "information.</p>"
            "<p><b>Cost and limits:</b> Usage is provider-metered. Akiha's "
            "5, 10, or 15 minute session limit bounds one session but is not "
            "a price guarantee. Context compression and bounded session "
            "resumption are always enabled.</p>"
            '<p><a href="https://ai.google.dev/gemini-api/docs/pricing">'
            "Review current Gemini API pricing and data-use labels</a></p>"
        )
        summary.setWordWrap(True)
        summary.setTextFormat(Qt.TextFormat.RichText)
        summary.setOpenExternalLinks(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            "I understand and allow cloud audio"
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addWidget(heading)
        layout.addWidget(summary)
        layout.addWidget(buttons)
        self.setLayout(layout)
