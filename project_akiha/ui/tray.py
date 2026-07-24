"""System tray controls for Project Akiha."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget


class AkihaTrayIcon(QSystemTrayIcon):
    """Tray icon with basic Phase 1 window controls."""

    def __init__(
        self,
        pet_window: QWidget,
        chat_window: QWidget,
        settings_window: QWidget,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._pet_window = pet_window
        self._chat_window = chat_window
        self._settings_window = settings_window

        self.setToolTip("Project Akiha")
        self.setIcon(_build_icon())
        self.setContextMenu(self._build_menu())
        self.activated.connect(self._handle_activation)

    def _build_menu(self) -> QMenu:
        menu = QMenu()

        show_action = QAction("Show", menu)
        show_action.triggered.connect(self._show_pet)
        menu.addAction(show_action)

        hide_action = QAction("Hide", menu)
        hide_action.triggered.connect(self._pet_window.hide)
        menu.addAction(hide_action)

        chat_action = QAction("Chat", menu)
        chat_action.triggered.connect(self._show_chat)
        menu.addAction(chat_action)

        settings_action = QAction("Settings", menu)
        settings_action.triggered.connect(self._show_settings)
        menu.addAction(settings_action)

        menu.addSeparator()

        quit_action = QAction("Quit", menu)
        app = QApplication.instance()
        if app is not None:
            quit_action.triggered.connect(app.quit)
        menu.addAction(quit_action)

        return menu

    def _handle_activation(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self._pet_window.isVisible():
                self._pet_window.hide()
            else:
                self._show_pet()

    def _show_pet(self) -> None:
        self._pet_window.show()
        self._pet_window.raise_()
        self._pet_window.activateWindow()

    def _show_settings(self) -> None:
        self._settings_window.show()
        self._settings_window.raise_()
        self._settings_window.activateWindow()

    def _show_chat(self) -> None:
        self._chat_window.show()
        self._chat_window.raise_()
        self._chat_window.activateWindow()

    def show_companion_message(self, title: str, message: str) -> None:
        """Show a non-modal companion tray message."""
        self.showMessage(
            title,
            message,
            QSystemTrayIcon.MessageIcon.Information,
            5000,
        )


def _build_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(147, 42, 68))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(8, 8, 48, 48)
    painter.setBrush(QColor(252, 232, 226))
    painter.drawEllipse(22, 24, 7, 7)
    painter.drawEllipse(36, 24, 7, 7)
    painter.end()

    return QIcon(pixmap)
