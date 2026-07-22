"""Application entry point for Project Akiha."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from project_akiha.config import load_config
from project_akiha.core.events.bus import EventBus
from project_akiha.core.state.animation import AnimationStateMachine
from project_akiha.ui.pet_window import PetWindow
from project_akiha.ui.tray import AkihaTrayIcon


def main() -> int:
    """Build the application graph and start the Qt event loop."""
    app = QApplication(sys.argv)
    app.setApplicationName("Project Akiha")
    app.setQuitOnLastWindowClosed(False)

    config = load_config()
    event_bus = EventBus()
    animation_state = AnimationStateMachine()
    window = PetWindow(
        event_bus=event_bus,
        animation_state=animation_state,
        config=config.pet_window,
    )
    window.move(config.pet_window.start_x, config.pet_window.start_y)
    window.show()

    tray_icon = AkihaTrayIcon(pet_window=window)
    tray_icon.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
