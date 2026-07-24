"""Qt delivery surface for proactive companion suggestions."""

from __future__ import annotations

from PySide6.QtWidgets import QSystemTrayIcon

from project_akiha.ui.chat_window import ChatWindow
from project_akiha.ui.tray import AkihaTrayIcon


class QtProactiveDeliverySurface:
    """Expose chat and tray delivery capabilities to the app layer."""

    def __init__(
        self,
        chat_window: ChatWindow,
        tray_icon: AkihaTrayIcon,
    ) -> None:
        self._chat_window = chat_window
        self._tray_icon = tray_icon

    def is_chat_visible(self) -> bool:
        """Return whether chat is currently visible."""
        return self._chat_window.isVisible()

    def append_chat_notice(self, message: str) -> None:
        """Append a quiet notice to the chat transcript."""
        self._chat_window.append_notice(message)

    def can_show_tray_message(self) -> bool:
        """Return whether tray messages are available."""
        return self._tray_icon.isVisible() and QSystemTrayIcon.supportsMessages()

    def show_tray_message(self, title: str, message: str) -> None:
        """Show a non-modal tray message."""
        self._tray_icon.show_companion_message(title, message)
